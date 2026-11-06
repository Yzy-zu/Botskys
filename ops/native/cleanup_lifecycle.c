/* Own x86_64 fixture: reentrant LIFO callbacks and fork/clone registration. */
#define _GNU_SOURCE
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern int __cxa_atexit(void (*function)(void *), void *argument, void *dso);
extern void *__dso_handle;
static char order[8];
static unsigned used;
static void callback(void *value) {
    char c = *(const char *)value;
    if (used >= sizeof(order) - 1) _Exit(30);
    order[used++] = c;
    if (c == 'B' && __cxa_atexit(callback, "C", __dso_handle)) _Exit(31);
}
static void report(void) {
    if (strcmp(order, "BCA")) {
        fprintf(stderr, "LIFO mismatch: %s\n", order);
        _Exit(32);
    }
    puts("CLEANUP_LIFECYCLE_PASS");
}
static int child(void *unused) {
    (void)unused;
    if (__cxa_atexit(callback, "X", __dso_handle)) _Exit(33);
    _Exit(0);
}
int main(void) {
    void *stack = malloc(1024 * 1024);
    if (!stack) return 34;
    for (unsigned i = 0; i < 8; ++i) {
        pid_t pid = i % 2 ? clone(child, (char *)stack + 1024 * 1024, SIGCHLD, NULL) : fork();
        if (pid == 0) child(NULL);
        if (pid < 0) return 35;
        int status;
        if (waitpid(pid, &status, 0) != pid || !WIFEXITED(status) || WEXITSTATUS(status)) return 36;
    }
    free(stack);
    if (atexit(report) || __cxa_atexit(callback, "A", __dso_handle) || __cxa_atexit(callback, "B", __dso_handle)) return 37;
    return 0;
}
