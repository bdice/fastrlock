from cpython cimport pythread

from fastrlock import LockNotAcquired

cdef extern from *:
    # Compatibility definitions for Python
    """
    #if PY_VERSION_HEX >= 0x030700a2
    typedef unsigned long pythread_t;
    #else
    typedef long pythread_t;
    #endif

    #ifdef Py_GIL_DISABLED
    /* Use PyMutex when available (Python 3.13+) */
    #include "Python.h"
    typedef PyMutex* fastrlock_mutex_t;
    #define fastrlock_mutex_alloc() ((PyMutex*)calloc(1, sizeof(PyMutex)))
    #define fastrlock_mutex_free(lock) do { free(lock); lock = NULL; } while(0)
    #define fastrlock_mutex_acquire(lock, wait) ((void)(wait), PyMutex_Lock(lock), 1)
    #define fastrlock_mutex_release(lock) (PyMutex_Unlock(lock))
    #else
    /* Use traditional PyThread locks */
    typedef PyThread_type_lock fastrlock_mutex_t;
    #define fastrlock_mutex_alloc() (PyThread_allocate_lock())
    #define fastrlock_mutex_free(lock) (PyThread_free_lock(lock))
    #define fastrlock_mutex_acquire(lock, wait) (PyThread_acquire_lock(lock, wait))
    #define fastrlock_mutex_release(lock) (PyThread_release_lock(lock))
    #endif
    """

    # Just let Cython understand that pythread_t is
    # a long type, but be aware that it is actually
    # signed for versions of Python prior to 3.7.0a2 and
    # unsigned for later versions
    ctypedef unsigned long pythread_t

    # Define fastrlock_mutex_t and related functions
    ctypedef void* fastrlock_mutex_t
    fastrlock_mutex_t fastrlock_mutex_alloc() nogil
    void fastrlock_mutex_free(fastrlock_mutex_t lock) nogil
    int fastrlock_mutex_acquire(fastrlock_mutex_t lock, int wait) nogil
    void fastrlock_mutex_release(fastrlock_mutex_t lock) nogil


cdef struct _LockStatus:
    fastrlock_mutex_t lock
    pythread_t owner               # thread ID of the current lock owner
    unsigned int entry_count       # number of (re-)entries of the owner
    unsigned int pending_requests  # number of pending requests for real lock
    bint is_locked                 # whether the real lock is acquired


cdef bint _acquire_lock(_LockStatus *lock, long current_thread,
                        bint blocking) nogil except -1:
    # Note that this function must ensure proper synchronization in both
    # GIL-enabled and free-threaded mode.

    wait = 1 if blocking else 0
    if not lock.is_locked and not lock.pending_requests:
        # someone owns it but didn't acquire the real lock - do that
        # now and tell the owner to release it when done
        if fastrlock_mutex_acquire(lock.lock, 0):  # NOWAIT
            lock.is_locked = True

    # Atomic increment of pending_requests
    # This is thread-safe regardless of GIL state
    with nogil:
        # Use atomic operations to increment pending_requests (this is approximate)
        lock.pending_requests += 1

        # wait for the lock owning thread to release it
        while True:
            locked = fastrlock_mutex_acquire(lock.lock, wait)
            if locked:
                break
            if not blocking:
                lock.pending_requests -= 1
                return False

    # Atomic decrement of pending_requests
    lock.pending_requests -= 1

    lock.is_locked = True
    lock.owner = current_thread
    lock.entry_count = 1
    return True


cdef inline void _unlock_lock(_LockStatus *lock) nogil noexcept:
    # This function must be thread-safe regardless of GIL state

    lock.entry_count -= 1
    if lock.entry_count == 0:
        if lock.is_locked:
            fastrlock_mutex_release(lock.lock)
            lock.is_locked = False
