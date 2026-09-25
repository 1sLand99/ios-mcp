#import "../MCPOCRRequestContext.h"
#include <assert.h>
#include <sys/socket.h>
#include <unistd.h>
int main(void) {
    @autoreleasepool {
        int sockets[2]; assert(!socketpair(AF_UNIX, SOCK_STREAM, 0, sockets));
        MCPOCRRequestContext *context = [MCPOCRRequestContext beginRequest:@1 session:@"a" socket:sockets[0]];
        assert(context && !context.shouldStop);
        assert(![MCPOCRRequestContext beginRequest:@1 session:@"a" socket:sockets[0]]);
        [MCPOCRRequestContext cancelRequest:@1 session:@"b"];
        assert(!context.shouldStop);
        [MCPOCRRequestContext cancelRequest:@"1" session:@"a"];
        assert(!context.shouldStop); // JSON string ID != numeric ID.
        [MCPOCRRequestContext cancelRequest:@1 session:@"a"];
        assert(context.shouldStop);
        [context finish]; assert(![MCPOCRRequestContext current]);
        context = [MCPOCRRequestContext beginRequest:@1 session:@"a" socket:sockets[0]];
        close(sockets[1]); assert(context.shouldStop); [context finish]; close(sockets[0]);
        context = [MCPOCRRequestContext beginRequest:@1 session:@"a" socket:-1];
        context.deadline = NSProcessInfo.processInfo.systemUptime - 1;
        assert(context.shouldStop); [context finish];
        puts("PASS cancellation context: session/typed ID isolation, duplicate IDs, cancellation, disconnect, deadline, cleanup");
    }
}
