#!/usr/bin/env python3
"""Compile the actual AppManager install method on macOS with installer doubles.

No device/app is installed. Tests extension routing and LS fallback options in
both normal and MCP_ROOTHIDE builds, not ZIP parsing or private iOS API behavior.
"""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r'''
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <assert.h>
#include <sys/stat.h>
#define APP_LOG(...) do {} while (0)
static NSString *root, *expectedPath;
static NSSet *helpers;
static BOOL helperOK, workspaceOK;
static NSUInteger calls, workspaceCalls, debCalls;
static NSMutableArray *executed;
NSString *MCPResolvedJailbreakPath(NSString *path) {
    NSString *name = path.lastPathComponent;
    return [root stringByAppendingPathComponent:[helpers containsObject:name] ? name : [@"missing-" stringByAppendingString:name]];
}
NSDictionary *MCPJailbreakEnvironment(void) { return @{}; }
BOOL MCPRunProcess(NSString *path, NSArray *args, NSDictionary *env, NSTimeInterval timeout,
                   NSUInteger maxOutput, NSString **output, int *status, NSString **error) {
    calls++;
    assert([args.lastObject isEqual:expectedPath]);
    [executed addObject:path.lastPathComponent];
    if (output) *output = @"fixture result";
    if (status) *status = helperOK ? 0 : 1;
    return YES;
}
@interface MCPTestWorkspace : NSObject
+ (instancetype)defaultWorkspace;
- (BOOL)installApplication:(NSURL *)url withOptions:(NSDictionary *)options error:(NSError **)error;
@end
@implementation MCPTestWorkspace
+ (instancetype)defaultWorkspace { return [self new]; }
- (BOOL)installApplication:(NSURL *)url withOptions:(NSDictionary *)options error:(NSError **)error {
    workspaceCalls++;
    assert([url.path isEqual:expectedPath]);
    assert(options.count == 0 || [options[@"PackageType"] isEqual:@"Customer"]);
    return workspaceOK;
}
@end
static Class MCPTestGetClass(const char *name) {
    assert(strcmp(name, "LSApplicationWorkspace") == 0);
    return MCPTestWorkspace.class;
}
// Route only the production method's class lookup to a uniquely named double;
// never replace/collide with macOS's actual LSApplicationWorkspace class.
#define objc_getClass MCPTestGetClass
@interface AppManager : NSObject
- (BOOL)installApp:(NSString *)path error:(NSString **)error;
- (BOOL)installDebPackage:(NSString *)path error:(NSString **)error;
- (NSString *)bundleIdFromIPA:(NSString *)path;
- (NSString *)bundleIdFromAppInstOutput:(NSString *)output;
- (BOOL)retryFakesignInstalledAppForBundleId:(NSString *)bundleId installedAfter:(NSDate *)date;
@end
@implementation AppManager
- (BOOL)installDebPackage:(NSString *)path error:(NSString **)error { debCalls++; return YES; }
- (NSString *)bundleIdFromIPA:(NSString *)path { return @"com.example.fixture"; }
- (NSString *)bundleIdFromAppInstOutput:(NSString *)output { return @"com.example.fixture"; }
- (BOOL)retryFakesignInstalledAppForBundleId:(NSString *)bundleId installedAfter:(NSDate *)date { return YES; }
'''

SUFFIX = r'''
@end
static void reset(void) { calls = workspaceCalls = debCalls = 0; executed = [NSMutableArray array]; }
int main(int argc, const char **argv) {
    @autoreleasepool {
        root = @(argv[1]);
        NSFileManager *fm = NSFileManager.defaultManager;
        for (NSString *name in @[@"mcp-root", @"mcp-roothelper", @"mcp-appinst"]) {
            NSString *path = [root stringByAppendingPathComponent:name];
            assert([fm createFileAtPath:path contents:[NSData data] attributes:nil]);
            assert(chmod(path.fileSystemRepresentation, 0755) == 0);
        }
        AppManager *manager = [AppManager new];
        NSUInteger checked = 0;
        for (NSString *ext in @[@"ipa", @"IPA", @"tipa", @"TIPA", @"TiPa"]) {
            expectedPath = [root stringByAppendingPathComponent:[@"test archive." stringByAppendingString:ext]];
            assert([fm createFileAtPath:expectedPath contents:[NSData data] attributes:nil]);
            // Missing helpers, successful CLI, and failed CLI -> LS fallback.
            for (NSUInteger mode = 0; mode < 3; mode++) {
                reset();
                helpers = mode ? [NSSet setWithObject:@"mcp-appinst"] : [NSSet set];
                helperOK = mode == 1; workspaceOK = YES;
                NSString *error = nil;
                assert([manager installApp:expectedPath error:&error]);
                assert(!debCalls && workspaceCalls == (mode == 1 ? 0 : 1));
                assert(calls == (mode ? 1 : 0)); checked++;
            }
#ifdef MCP_ROOTHIDE
            // RootHide delegation keeps the original .tipa path.
            for (NSUInteger variant = 0; variant < 2; variant++) {
                BOOL viaRoot = variant != 0;
                reset(); helperOK = YES;
                helpers = viaRoot ? [NSSet setWithArray:@[@"mcp-root", @"mcp-roothelper"]] : [NSSet setWithObject:@"mcp-roothelper"];
                assert([manager installApp:expectedPath error:nil]);
                assert(calls == 1 && workspaceCalls == 0 && debCalls == 0);
                assert([executed[0] isEqual:viaRoot ? @"mcp-root" : @"mcp-roothelper"]); checked++;
            }
#endif
            reset(); helpers = [NSSet set]; workspaceOK = NO;
            NSString *failure = nil;
            assert(![manager installApp:expectedPath error:&failure]);
            assert(failure.length > 0 && workspaceCalls == 2); checked++;
        }
        helpers = [NSSet set]; workspaceOK = YES;
        for (NSString *name in @[@"app.zip", @"app.tipa.zip", @"app.ipa.tmp", @"noextension"]) {
            reset(); expectedPath = [root stringByAppendingPathComponent:name];
            assert([fm createFileAtPath:expectedPath contents:[NSData data] attributes:nil]);
            NSString *error = nil;
            assert(![manager installApp:expectedPath error:&error]);
            assert([error containsString:@"expected .ipa, .tipa or .deb"]);
            assert(!calls && !workspaceCalls && !debCalls); checked++;
        }
        for (NSString *name in @[@"package.deb", @"package.DEB"]) {
            reset(); expectedPath = [root stringByAppendingPathComponent:name];
            assert([fm createFileAtPath:expectedPath contents:[NSData data] attributes:nil]);
            assert([manager installApp:expectedPath error:nil]);
            assert(debCalls == 1 && !calls && !workspaceCalls); checked++;
        }
        reset(); assert(![manager installApp:@"" error:nil]); checked++;
        assert(![manager installApp:[root stringByAppendingPathComponent:@"missing.tipa"] error:nil]); checked++;
        assert(!calls && !workspaceCalls && !debCalls);
        printf("PASS %lu install routing checks (installer doubles)\n", (unsigned long)checked);
    }
}
'''

def main():
    source = (ROOT / 'AppManager.m').read_text()
    begin = source.index('- (BOOL)installApp:')
    end = source.index('\n- (NSString *)bundleIdFromIPA:', begin)
    method = source[begin:end]
    with tempfile.TemporaryDirectory(prefix='ios-mcp-install-routing-') as tmp:
        work = Path(tmp)
        harness = work / 'test.m'
        harness.write_text(PREFIX + method + SUFFIX)
        for scheme, defines in [('normal', []), ('roothide', ['-DMCP_ROOTHIDE=1'])]:
            binary = work / ('test-' + scheme)
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fblocks', '-Wall', '-Werror',
                            *defines, '-framework', 'Foundation', str(harness), '-o', str(binary)], check=True)
            fixture = work / scheme
            fixture.mkdir()
            subprocess.run([str(binary), str(fixture)], check=True)

if __name__ == '__main__':
    main()
