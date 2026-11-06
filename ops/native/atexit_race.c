/* Own synthetic Box64 regression: register C++ destructors concurrently.
 * No game/world/network. Exit verifies every callback, not just process startup.
 * Build for x86_64 with -O1 -pthread; run only in the explicitly scoped lab.
 */
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>

extern int __cxa_atexit(void (*function)(void *), void *argument, void *dso);
extern void *__dso_handle;

enum { THREADS = 16, PER_THREAD = 2048 };
static pthread_barrier_t barrier;
static _Atomic unsigned completed;

static void destructor(void *unused) {
    (void)unused;
    atomic_fetch_add_explicit(&completed, 1, memory_order_relaxed);
}
static void report(void) {
    unsigned actual = atomic_load_explicit(&completed, memory_order_relaxed);
    printf("CALLBACKS=%u EXPECTED=%u\n", actual, THREADS * PER_THREAD);
    fflush(stdout);
    if (actual != THREADS * PER_THREAD) _Exit(23);
    puts("ATEXIT_RACE_PASS");
}
static void *register_callbacks(void *unused) {
    (void)unused;
    pthread_barrier_wait(&barrier);
    for (unsigned i = 0; i < PER_THREAD; ++i)
        if (__cxa_atexit(destructor, NULL, __dso_handle)) _Exit(24);
    return NULL;
}
int main(void) {
    pthread_t threads[THREADS];
    if (atexit(report) || pthread_barrier_init(&barrier, NULL, THREADS)) return 25;
    puts("ATEXIT_RACE_BEGIN");
    fflush(stdout);
    for (unsigned i = 0; i < THREADS; ++i)
        if (pthread_create(&threads[i], NULL, register_callbacks, NULL)) _Exit(26);
    for (unsigned i = 0; i < THREADS; ++i)
        if (pthread_join(threads[i], NULL)) _Exit(27);
    pthread_barrier_destroy(&barrier);
    puts("REGISTRATION_FINISHED");
    return 0;
}
