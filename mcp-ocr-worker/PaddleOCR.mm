#import "PaddleOCR.h"
#import <ImageIO/ImageIO.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CommonCrypto/CommonDigest.h>
#include <onnxruntime_cxx_api.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include "../third_party/paddleocr/clipper/clipper.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <unistd.h>

namespace {
using Quad = std::array<cv::Point2f, 4>;
void require(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message);
}
std::string sha256(NSData *data) {
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, bytes);
    char hex[CC_SHA256_DIGEST_LENGTH * 2 + 1];
    for (unsigned i = 0; i < sizeof(bytes); ++i) snprintf(hex + i * 2, 3, "%02x", bytes[i]);
    return hex;
}
// A CGBitmapContext's backing rows match CGImage scanline order. Do not apply the
// UIKit drawing flip here: it would vertically mirror the pixels fed to OpenCV.
cv::Mat decode(NSData *data) {
    require(data.length > 0 && data.length <= 24 * 1024 * 1024, "image payload exceeds limit or is empty");
    CGImageSourceRef source = CGImageSourceCreateWithData((__bridge CFDataRef)data, NULL);
    require(source != NULL, "invalid image");
    NSDictionary *properties = CFBridgingRelease(CGImageSourceCopyPropertiesAtIndex(source, 0, NULL));
    size_t w = [properties[(id)kCGImagePropertyPixelWidth] unsignedIntegerValue];
    size_t h = [properties[(id)kCGImagePropertyPixelHeight] unsignedIntegerValue];
    if (!w || !h || w > 8192 || h > 8192 || w * h > 16000000) {
        CFRelease(source); throw std::runtime_error("image dimensions exceed 16 megapixel / 8192 edge limit");
    }
    CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, NULL);
    CFRelease(source);
    require(image != NULL, "image decoding failed");
    cv::Mat rgba((int)h, (int)w, CV_8UC4);
    CGColorSpaceRef color = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(rgba.data, w, h, 8, rgba.step, color,
                                  kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(color);
    if (!ctx) { CGImageRelease(image); throw std::runtime_error("image context allocation failed"); }
    CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), image);
    CGContextRelease(ctx); CGImageRelease(image);
    cv::Mat bgr;
    cv::cvtColor(rgba, bgr, cv::COLOR_RGBA2BGR);
    return bgr;
}
Quad corners(const cv::RotatedRect &rect) {
    cv::Point2f p[4]; rect.points(p);
    std::sort(p, p + 4, [](auto a, auto b) { return a.x < b.x; });
    Quad q;
    q[0] = p[p[0].y < p[1].y ? 0 : 1]; q[3] = p[p[0].y < p[1].y ? 1 : 0];
    q[1] = p[p[2].y < p[3].y ? 2 : 3]; q[2] = p[p[2].y < p[3].y ? 3 : 2];
    return q;
}
std::vector<float> normalize(const cv::Mat &bgr, int paddedWidth, bool detection) {
    size_t plane = (size_t)bgr.rows * paddedWidth;
    std::vector<float> tensor(plane * 3, 0.f); // Rec right padding is zero AFTER normalization.
    const float means[] = {.485f, .456f, .406f}, stds[] = {.229f, .224f, .225f};
    for (int y = 0; y < bgr.rows; y++) {
        const cv::Vec3b *row = bgr.ptr<cv::Vec3b>(y);
        for (int x = 0; x < bgr.cols; x++) for (int c = 0; c < 3; c++) {
            float value = row[x][c] / 255.f;
            tensor[c * plane + y * paddedWidth + x] = detection ? (value - means[c]) / stds[c] : value * 2.f - 1.f;
        }
    }
    return tensor;
}
struct Runtime {
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "ios-mcp-paddleocr"};
    std::unique_ptr<Ort::Session> det, rec;
    Runtime(NSString *directory) {
        cv::setNumThreads(1);
        auto providers = Ort::GetAvailableProviders();
        require(providers.size() == 1 && providers[0] == "CPUExecutionProvider", "runtime must contain CPUExecutionProvider ONLY");
        Ort::SessionOptions options;
        options.SetIntraOpNumThreads(2);
        options.SetInterOpNumThreads(1);
        options.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        options.DisableCpuMemArena(); // Prevent retained arenas from growing with dynamic input sizes.
        options.DisableMemPattern();
        options.AddConfigEntry("session.intra_op.allow_spinning", "0");
        options.AddConfigEntry("session.inter_op.allow_spinning", "0");
        // CPU EP is registered by ORT by default. Do not append ANY accelerator provider.
        det = std::make_unique<Ort::Session>(env, [directory stringByAppendingPathComponent:@"det.onnx"].fileSystemRepresentation, options);
        rec = std::make_unique<Ort::Session>(env, [directory stringByAppendingPathComponent:@"rec.onnx"].fileSystemRepresentation, options);
        for (auto *session : {det.get(), rec.get()}) {
            require(session->GetInputCount() == 1 && session->GetOutputCount() == 1, "unexpected model inputs/outputs");
            require(session->GetInputTypeInfo(0).GetTensorTypeAndShapeInfo().GetElementType() == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,
                    "model input must be float32");
        }
        fprintf(stderr, "[PaddleOCR] initialized ORT=%s provider=CPUExecutionProvider pid=%d\n", OrtGetApiBase()->GetVersionString(), getpid());
    }
    Ort::Value run(Ort::Session &session, std::vector<float> &input, int h, int w) {
        std::array<int64_t, 4> shape{1, 3, h, w};
        auto info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        auto tensor = Ort::Value::CreateTensor<float>(info, input.data(), input.size(), shape.data(), shape.size());
        const char *inputs[] = {"x"}, *outputs[] = {"fetch_name_0"};
        auto result = session.Run(Ort::RunOptions{nullptr}, inputs, &tensor, 1, outputs, 1);
        require(result[0].IsTensor(), "model output is not a tensor");
        require(result[0].GetTensorTypeAndShapeInfo().GetElementType() == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,
                "model output must be float32");
        return std::move(result[0]);
    }
};
std::vector<Quad> detect(Runtime &runtime, const cv::Mat &image) {
    // Exact DetResizeForTest resize_long=960: floor scaled sides then ceil to stride 128.
    double ratio = 960. / std::max(image.cols, image.rows);
    int w = std::max(128, (((int)(image.cols * ratio) + 127) / 128) * 128);
    int h = std::max(128, (((int)(image.rows * ratio) + 127) / 128) * 128);
    cv::Mat resized; cv::resize(image, resized, cv::Size(w, h), 0, 0, cv::INTER_LINEAR);
    auto input = normalize(resized, w, true);
    auto output = runtime.run(*runtime.det, input, h, w);
    auto shape = output.GetTensorTypeAndShapeInfo().GetShape();
    require(shape.size() == 4 && shape[0] == 1 && shape[1] == 1 && shape[2] == h && shape[3] == w,
            "unexpected detector output shape");
    cv::Mat probabilities(h, w, CV_32F, output.GetTensorMutableData<float>()), bitmap;
    cv::compare(probabilities, .3, bitmap, cv::CMP_GT);
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(bitmap, contours, cv::RETR_LIST, cv::CHAIN_APPROX_SIMPLE);
    std::vector<Quad> boxes;
    for (size_t i = 0; i < std::min(contours.size(), (size_t)1000); i++) {
        if (contours[i].size() < 3) continue;
        auto rect = cv::minAreaRect(contours[i]);
        if (std::min(rect.size.width, rect.size.height) < 3) continue;
        Quad q = corners(rect);
        cv::Rect bounds = cv::boundingRect(std::vector<cv::Point2f>(q.begin(), q.end())) & cv::Rect(0, 0, w, h);
        if (bounds.empty()) continue;
        cv::Mat mask(bounds.size(), CV_8U, cv::Scalar(0));
        std::vector<cv::Point> polygon;
        for (auto p : q) polygon.emplace_back((int)floor(p.x) - bounds.x, (int)floor(p.y) - bounds.y);
        cv::fillPoly(mask, std::vector<std::vector<cv::Point>>{polygon}, cv::Scalar(1));
        if (cv::mean(probabilities(bounds), mask)[0] < .6) continue;
        std::vector<cv::Point2f> points(q.begin(), q.end());
        double perimeter = cv::arcLength(points, true);
        if (perimeter <= 0) continue;
        double distance = std::abs(cv::contourArea(points)) * 1.5 / perimeter;
        ClipperLib::Path path;
        for (auto p : q) path.emplace_back((ClipperLib::cInt)std::lround(p.x * 1024), (ClipperLib::cInt)std::lround(p.y * 1024));
        ClipperLib::ClipperOffset offset;
        offset.AddPath(path, ClipperLib::jtRound, ClipperLib::etClosedPolygon);
        ClipperLib::Paths expanded;
        offset.Execute(expanded, distance * 1024);
        if (expanded.size() != 1) continue;
        points.clear();
        for (auto p : expanded[0]) points.emplace_back(p.X / 1024.f, p.Y / 1024.f);
        if (points.size() < 3) continue;
        rect = cv::minAreaRect(points);
        if (std::min(rect.size.width, rect.size.height) < 5) continue;
        q = corners(rect);
        for (auto &p : q) {
            p.x = std::clamp(p.x * image.cols / w, 0.f, (float)image.cols - 1);
            p.y = std::clamp(p.y * image.rows / h, 0.f, (float)image.rows - 1);
        }
        boxes.push_back(q);
    }
    require(boxes.size() <= 128, "too many text lines (limit 128); use a smaller region");
    // Stable strict ordering, then same-row insertion like Paddle sorted_boxes.
    std::sort(boxes.begin(), boxes.end(), [](const Quad &a, const Quad &b) {
        return a[0].y == b[0].y ? a[0].x < b[0].x : a[0].y < b[0].y;
    });
    for (size_t i = 1; i < boxes.size(); i++) for (size_t j = i; j > 0; j--) {
        if (std::abs(boxes[j][0].y - boxes[j-1][0].y) < 10 && boxes[j][0].x < boxes[j-1][0].x)
            std::swap(boxes[j], boxes[j-1]);
        else break;
    }
    return boxes;
}
cv::Mat crop(const cv::Mat &image, const Quad &q) {
    int w = std::max(cv::norm(q[0] - q[1]), cv::norm(q[2] - q[3]));
    int h = std::max(cv::norm(q[0] - q[3]), cv::norm(q[1] - q[2]));
    require(w > 0 && h > 0 && w <= 8192 && h <= 8192, "invalid detected text crop");
    Quad target{{{0, 0}, {(float)w, 0}, {(float)w, (float)h}, {0, (float)h}}};
    auto transform = cv::getPerspectiveTransform(q.data(), target.data());
    cv::Mat result;
    cv::warpPerspective(image, result, transform, cv::Size(w, h), cv::INTER_CUBIC, cv::BORDER_REPLICATE);
    if (h >= w * 1.5) cv::rotate(result, result, cv::ROTATE_90_COUNTERCLOCKWISE);
    return result;
}
}

@implementation PaddleOCR {
    NSString *_directory;
    NSArray<NSString *> *_dictionary;
    NSDictionary *_hashes;
    std::unique_ptr<Runtime> _runtime;
}
- (instancetype)initWithResourceDirectory:(NSString *)directory {
    if ((self = [super init])) {
        _directory = [directory copy];
        _hashes = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:@"sha256.json"]] ?: [NSData data]
                                                 options:0 error:nil];
        require([_hashes isKindOfClass:NSDictionary.class], "missing resource checksum manifest");
        [self checkResources];
        _dictionary = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:@"dictionary.json"]]
                                                     options:0 error:nil];
        require([_dictionary isKindOfClass:NSArray.class] && _dictionary.count == 18385, "invalid PP-OCRv5 dictionary");
        for (id entry in _dictionary) require([entry isKindOfClass:NSString.class], "invalid dictionary entry");
        _runtime = std::make_unique<Runtime>(directory);
    }
    return self;
}
- (void)checkResources {
    // Verify on EVERY request, including warm sessions: removal/corruption must never be hidden.
    for (NSString *name in @[@"det.onnx", @"rec.onnx", @"dictionary.json"]) {
        NSData *data = [NSData dataWithContentsOfFile:[_directory stringByAppendingPathComponent:name]
                                             options:NSDataReadingMappedIfSafe error:nil];
        require(data != nil && data.length <= 32 * 1024 * 1024, "model/dictionary missing or oversized");
        NSString *expected = _hashes[name];
        require([expected isKindOfClass:NSString.class] && sha256(data) == expected.UTF8String, "model/dictionary checksum mismatch");
    }
}
- (NSDictionary *)recognize:(NSDictionary *)request {
    [self checkResources];
    NSData *imageData = [[NSData alloc] initWithBase64EncodedString:request[@"image"] options:0];
    cv::Mat image = decode(imageData);
    int orientation = [request[@"orientation"] intValue];
    if (orientation == 3) cv::rotate(image, image, cv::ROTATE_180);
    else if (orientation == 6) cv::rotate(image, image, cv::ROTATE_90_CLOCKWISE);
    else if (orientation == 8) cv::rotate(image, image, cv::ROTATE_90_COUNTERCLOCKWISE);
    else require(orientation == 1, "unsupported image orientation");
    int fullW = image.cols, fullH = image.rows;
    NSArray *roi = request[@"roi"];
    require([roi isKindOfClass:NSArray.class] && roi.count == 4, "invalid ROI");
    double v[4];
    for (int i = 0; i < 4; i++) {
        require([roi[i] isKindOfClass:NSNumber.class], "invalid ROI value");
        v[i] = [roi[i] doubleValue];
        require(std::isfinite(v[i]) && v[i] >= 0 && v[i] <= 1, "ROI outside normalized image");
    }
    require(v[0] + v[2] <= 1.000001 && v[1] + v[3] <= 1.000001, "ROI extends beyond image");
    int x = std::clamp((int)floor(v[0] * fullW), 0, fullW);
    int y = std::clamp((int)floor(v[1] * fullH), 0, fullH);
    int right = std::clamp((int)ceil((v[0] + v[2]) * fullW), x, fullW);
    int bottom = std::clamp((int)ceil((v[1] + v[3]) * fullH), y, fullH);
    NSMutableArray *texts = [NSMutableArray array];
    if (right > x && bottom > y) {
        cv::Mat region = image(cv::Rect(x, y, right - x, bottom - y));
        auto boxes = detect(*_runtime, region);
        double minConfidence = [request[@"min_confidence"] doubleValue];
        require(std::isfinite(minConfidence) && minConfidence >= 0 && minConfidence <= 1, "invalid confidence threshold");
        for (const auto &box : boxes) {
            cv::Mat line = crop(region, box), resized;
            int contentW = std::max(1, (int)ceil(48. * line.cols / line.rows));
            require(contentW <= 2048, "text line too wide (2048 normalized pixels); use a smaller region");
            int inputW = std::max(320, contentW);
            cv::resize(line, resized, cv::Size(contentW, 48), 0, 0, cv::INTER_LINEAR);
            auto input = normalize(resized, inputW, false);
            auto output = _runtime->run(*_runtime->rec, input, 48, inputW);
            auto shape = output.GetTensorTypeAndShapeInfo().GetShape();
            require(shape.size() == 3 && shape[0] == 1 && shape[2] == (int64_t)_dictionary.count && shape[1] <= 2048,
                    "recognizer output/dictionary mismatch");
            const float *data = output.GetTensorData<float>();
            NSMutableString *text = [NSMutableString string];
            double confidence = 0; int count = 0; int previous = -1;
            for (int t = 0; t < shape[1]; t++) {
                const float *row = data + t * shape[2];
                int index = (int)(std::max_element(row, row + shape[2]) - row);
                float probability = row[index];
                require(std::isfinite(probability) && probability >= 0 && probability <= 1.001, "invalid CTC probabilities");
                if (index && index != previous) {
                    [text appendString:_dictionary[index]]; confidence += probability; count++;
                }
                previous = index;
            }
            if (!count || confidence / count < minConfidence) continue;
            float left = fullW, top = fullH, r = 0, b = 0;
            for (auto p : box) { left = std::min(left, p.x + x); top = std::min(top, p.y + y); r = std::max(r, p.x + x); b = std::max(b, p.y + y); }
            [texts addObject:@{@"text": text, @"confidence": @(confidence / count),
                @"box": @[@(left / fullW), @(top / fullH), @((r - left) / fullW), @((b - top) / fullH)]}];
        }
    }
    return @{@"texts": texts, @"provider": @"CPUExecutionProvider", @"runtime": @"onnxruntime-1.20.1",
             @"model": @"PP-OCRv5_mobile", @"worker_pid": @(getpid())};
}
@end
