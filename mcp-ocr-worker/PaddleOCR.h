#import <Foundation/Foundation.h>

// No UIKit/Vision dependency: this class only runs inside the disposable worker.
@interface PaddleOCR : NSObject
- (instancetype)initWithResourceDirectory:(NSString *)directory;
- (NSDictionary *)recognize:(NSDictionary *)request;
@end
