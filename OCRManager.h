#import <Foundation/Foundation.h>

/// On-device OCR via the Vision framework. Captures the current screen, recognizes text,
/// and returns each text block with screen-point coordinates (ready for tap_screen).
@interface OCRManager : NSObject

+ (instancetype)sharedInstance;

/// Validate an optional region before capture/recognition. nil means full screen.
+ (BOOL)validateRegion:(NSDictionary *)region error:(NSString **)error;

/// Recognize text on the current screen.
///   languages:     recognition languages (e.g. @[@"zh-Hans", @"en"]); nil = default.
///   minConfidence: drop results below this confidence (0..1).
///   region:        optional screen-point rect {x,y,width,height} to limit OCR; nil = full screen.
///                  All fields must be finite numbers, width/height > 0. Partly off-screen regions
///                  are clipped; wholly off-screen regions return no texts. Invalid regions fail.
///   fast:          YES prefers fast recognition (MCP default); automatically uses accurate if
///                  the requested languages are unsupported by fast (e.g. Chinese). NO = accurate.
/// Accurate recognition runs on CPU directly; failures return an error without retry or downgrade.
/// Returns "texts" (text/confidence/rect/tap), "count", "screen", and "recognition" (actual
/// level/languages/revision/CPU configuration), or nil with *error.
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages
                               minConfidence:(double)minConfidence
                                      region:(NSDictionary *)region
                                        fast:(BOOL)fast
                                       error:(NSString **)error;

@end
