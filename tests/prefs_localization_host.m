#import <Foundation/Foundation.h>
#import <dlfcn.h>

// Load the real localization code in a plugin, just as Settings loads our bundle.
// This catches accidentally using NSBundle.mainBundle for translation resources.
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 3) return 2;
        NSBundle *bundle = [NSBundle bundleWithPath:@(argv[1])];
        NSError *error = nil;
        if (![bundle loadAndReturnError:&error]) {
            fprintf(stderr, "%s\n", error.description.UTF8String);
            return 3;
        }
        NSString *(*localize)(NSString *) = dlsym(RTLD_DEFAULT, "IOSMCPLocalizedString");
        if (!localize) return 4;
        NSData *input = [NSData dataWithContentsOfFile:@(argv[2])];
        NSArray *keys = [NSJSONSerialization JSONObjectWithData:input options:0 error:&error];
        if (![keys isKindOfClass:NSArray.class]) return 5;
        NSMutableDictionary *strings = [NSMutableDictionary dictionary];
        for (NSString *key in keys) strings[key] = localize(key);
        NSData *result = [NSJSONSerialization dataWithJSONObject:strings options:0 error:&error];
        if (!result) return 6;
        fwrite(result.bytes, 1, result.length, stdout);
    }
    return 0;
}
