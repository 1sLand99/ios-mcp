#import "../OCRManager.h"
#import "../VisionOCREngine.h"
#import "../PaddleOCRManager.h"
#import "../MCPLogger.h"
#include <assert.h>

// Test doubles ONLY in this test binary: production router is compiled unchanged.
@implementation MCPLogger
+ (void)log:(NSString *)format, ... {}
@end
@implementation VisionOCREngine
+ (instancetype)sharedInstance { return [self new]; }
+ (BOOL)validateRegion:(NSDictionary *)region error:(NSString **)error { return YES; }
- (NSDictionary *)recognizeTextWithLanguages:(NSArray *)languages minConfidence:(double)c region:(NSDictionary *)r fast:(BOOL)fast error:(NSString **)e {
    return @{@"recognition": @{@"engine": @"vision"}};
}
@end
@implementation PaddleOCRManager
+ (instancetype)sharedInstance { return [self new]; }
- (NSDictionary *)recognizeTextWithLanguages:(NSArray *)languages minConfidence:(double)c region:(NSDictionary *)r fast:(BOOL)fast error:(NSString **)e {
    if ([languages containsObject:@"fail-test"]) { if (e) *e = @"model failed"; return nil; }
    return @{@"recognition": @{@"engine": @"paddleocr"}};
}
@end
int main(void) {
    @autoreleasepool {
        OCRManager *manager = OCRManager.sharedInstance;
        for (id engine in @[@"paddleocr", NSNull.null, @"vision", NSNull.null]) {
            NSString *value = engine == NSNull.null ? nil : engine;
            NSDictionary *result = [manager recognizeTextWithLanguages:nil minConfidence:.3 region:nil fast:YES engine:value error:nil];
            assert([result[@"recognition"][@"engine"] isEqual:value ?: @"paddleocr"]);
        }
        for (id bad in @[@"", @"VISION", @"other", @1, NSNull.null, @[]]) {
            NSString *error;
            assert(![manager recognizeTextWithLanguages:nil minConfidence:.3 region:nil fast:YES engine:bad error:&error]);
            assert([error containsString:@"Invalid engine"]);
        }
        NSString *error;
        assert(![manager recognizeTextWithLanguages:@[@"fail-test"] minConfidence:.3 region:nil fast:YES engine:@"paddleocr" error:&error]);
        assert([error containsString:@"paddleocr"]);
        assert(![manager recognizeTextWithLanguages:@[@"fail-test"] minConfidence:.3 region:nil fast:YES engine:nil error:&error]);
        assert([error containsString:@"paddleocr"]); // Default failure must not retry Vision.
        NSDictionary *vision = [manager recognizeTextWithLanguages:@[@"fail-test"] minConfidence:.3 region:nil fast:YES engine:@"vision" error:&error];
        assert([vision[@"recognition"][@"engine"] isEqual:@"vision"]);
        NSDictionary *legacy = [manager recognizeTextWithLanguages:nil minConfidence:.3 region:nil fast:YES error:nil];
        assert([legacy[@"recognition"][@"engine"] isEqual:@"paddleocr"]);
        assert([[OCRManager defaultEngine] isEqual:@"paddleocr"]);
        dispatch_apply(200, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t i) {
            @autoreleasepool {
                NSString *engine = i % 3 == 0 ? @"vision" : (i % 3 == 1 ? @"paddleocr" : nil);
                NSDictionary *result = [manager recognizeTextWithLanguages:nil minConfidence:.3 region:nil fast:YES engine:engine error:nil];
                assert([result[@"recognition"][@"engine"] isEqual:engine ?: @"paddleocr"]);
            }
        });
        puts("PASS production router: legacy/default/explicit/invalid/failure isolation/200 concurrent calls (engine doubles)");
    }
}
