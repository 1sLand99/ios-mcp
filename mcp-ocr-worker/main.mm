#import "PaddleOCR.h"
#import <Foundation/Foundation.h>
#include <arpa/inet.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>
#include <mach/mach.h>
#include <thread>
#include <chrono>
#include <stdexcept>

static bool transfer(int fd, void *bytes, size_t length, bool writing) {
    auto *p = (uint8_t *)bytes;
    while (length) {
        pollfd f{fd, (short)(writing ? POLLOUT : POLLIN), 0};
        int ready;
        do { ready = poll(&f, 1, 60000); } while (ready < 0 && errno == EINTR);
        if (ready <= 0) return false; // Idle shutdown releases both model sessions.
        ssize_t n = writing ? write(fd, p, length) : read(fd, p, length);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        p += n; length -= n;
    }
    return true;
}
int main(int argc, char **argv) {
    @autoreleasepool {
        signal(SIGPIPE, SIG_IGN);
        if (argc != 3 || strcmp(argv[1], "--resources")) return 64;
        NSString *resources = @(argv[2]);
        // Bounds peak physical footprint even if an allocator/operator misbehaves.
        std::thread([] {
            while (true) {
                task_vm_info_data_t info{}; mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
                if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) == KERN_SUCCESS &&
                    info.phys_footprint > 512ULL * 1024 * 1024) _exit(75);
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        }).detach();
        PaddleOCR *engine = nil;
        while (true) {
            @autoreleasepool {
                uint32_t length;
                if (!transfer(STDIN_FILENO, &length, sizeof(length), false)) break;
                length = ntohl(length);
                if (!length || length > 32 * 1024 * 1024) return 65;
                NSMutableData *data = [NSMutableData dataWithLength:length];
                if (!transfer(STDIN_FILENO, data.mutableBytes, length, false)) break;
                NSDictionary *response;
                try {
                    @try {
                        id request = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
                        if (![request isKindOfClass:NSDictionary.class]) throw std::runtime_error("invalid request");
                        if (!engine) engine = [[PaddleOCR alloc] initWithResourceDirectory:resources];
                        response = [engine recognize:request];
                    } @catch (NSException *e) {
                        response = @{@"error": [@"PaddleOCR: " stringByAppendingString:e.reason ?: e.name]};
                        engine = nil;
                    }
                } catch (const std::exception &e) {
                    response = @{@"error": [NSString stringWithFormat:@"PaddleOCR: %s", e.what()]};
                    engine = nil;
                }
                NSData *out = [NSJSONSerialization dataWithJSONObject:response options:0 error:nil];
                if (!out || out.length > 1024 * 1024) return 65;
                length = htonl((uint32_t)out.length);
                if (!transfer(STDOUT_FILENO, &length, sizeof(length), true) ||
                    !transfer(STDOUT_FILENO, (void *)out.bytes, out.length, true)) break;
            }
        }
    }
    return 0;
}
