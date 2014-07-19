from __future__ import absolute_import


__all__ = ('CallbackDeque', 'CallbackQueue', 'ScheduledEventLoop')

from collections import defaultdict, deque
from threading import RLock, Event, Thread
from kivy.clock import Clock
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
import six
import sys


class CallbackDeque(deque):
    '''
    A Multithread safe class that calls a callback whenever an item is added
    to the queue. Instead of having to poll or wait, you could wait to get
    notified of additions.


    :Parameters:
        `callback`: callable
            The function to call when adding to the queue
    '''

    callback = None

    def __init__(self, callback, **kwargs):
        deque.__init__(self, **kwargs)
        self.callback = callback

    def append(self, x, *largs, **kwargs):
        deque.append(self, (x, largs, kwargs))
        self.callback()

    def appendleft(self, x, *largs, **kwargs):
        deque.appendleft(self, (x, largs, kwargs))
        self.callback()


class CallbackQueue(Queue):
    '''
    A Multithread safe class that calls a callback whenever an item is added
    to the queue. Instead of having to poll or wait, you could wait to get
    notified of additions.

    >>> def callabck():
    ...     print('Added')
    >>> q = KivyQueue(notify_func=callabck)
    >>> q.put('test', 55)
    Added
    >>> q.get()
    ('test', 55)

    :Parameters:
        `notify_func`: callable
            The function to call when adding to the queue
    '''

    notify_func = None

    def __init__(self, notify_func, **kwargs):
        Queue.__init__(self, **kwargs)
        self.notify_func = notify_func

    def put(self, key, val):
        '''
        Adds a (key, value) tuple to the queue and calls the callback function.
        '''
        Queue.put(self, (key, val), False)
        self.notify_func()

    def get(self):
        '''
        Returns the next items in the queue, if non-empty, otherwise a
        :py:attr:`Queue.Empty` exception is raised.
        '''
        return Queue.get(self, False)


class ScheduledEvent(object):

    repeat = False
    func_kwargs = None
    callback = None
    scheduled_callbacks = None
    trigger = False
    completed = False
    unique = False

    def __init__(self, callback=None, func_kwargs={}, repeat=False,
                 trigger=False, unique=True, **kwargs):
        self.callback = callback
        self.func_kwargs = func_kwargs
        self.repeat = repeat
        self.scheduled_callbacks = []
        self.trigger = trigger
        self.unique = unique


class ScheduledEventLoop(object):

    __callback_lock = None
    __thread_event = None
    __thread = None
    __signal_exit = False
    __callbacks = None
    __current_callback = None
    _kivy_trigger = None
    target = None

    def __init__(self, target=None, **kwargs):
        super(ScheduledEventLoop, self).__init__(**kwargs)
        self.__callback_lock = RLock()
        self.__thread_event = Event()
        self.__callbacks = defaultdict(list)
        self._kivy_trigger = Clock.create_trigger(self._service_kivy_thread)
        self.__thread = Thread(target=self._callback_thread)
        self.__thread.start()
        self.target = target

    def __del__(self):
        self.__signal_exit = True
        self.__thread_event.set()
        super(ScheduledEventLoop, self).__del__()

    def request_callback(self, name, callback=None, trigger=False,
                         repeat=False, unique=True, **kwargs):
        ''' If not repeat and not unique, after the first call to name it'd be
        considered complete.
        '''
        lock = self.__callback_lock

        ev = ScheduledEvent(callback=callback, func_kwargs=kwargs,
                            repeat=repeat, trigger=trigger, unique=unique)
        lock.acquire()
        self.__callbacks[name].append(ev)
        lock.release()
        if trigger:
            self.__thread_event.set()
        return ev

    def remove_request(self, name, callback_id, **kwargs):
        callbacks = self.__callbacks
        lock = self.__callback_lock

        if name in callbacks:
            lock.acquire()
            callbacks = callbacks[name]
            lock.release()
            try:
                callbacks.remove(callback_id)
            except ValueError:
                pass

    def _schedule_thread_callbacks(self, name, result, callbacks,
                                   src_callbacks, event):
        got_callback = False
        for ev in callbacks:
            if (ev.unique and ev is not event) or ev not in src_callbacks:
                continue

            if ev.callback is None:
                if not ev.repeat:
                    try:
                        src_callbacks.remove(ev)
                    except ValueError:
                        pass
                continue

            ev.scheduled_callbacks.append(result)
            if not ev.repeat:
                ev.completed = True
            got_callback = True

        return got_callback

    def _service_kivy_thread(self, dt):
        callbacks = self.__callbacks
        keys = callbacks.keys()

        for name in keys:
            cb = callbacks[name]
            c = list(cb)
            for ev in c:
                if not len(ev.scheduled_callbacks):
                    continue

                scheduled_callbacks = list(ev.scheduled_callbacks)
                del ev.scheduled_callbacks[:len(scheduled_callbacks)]
                callback = ev.callback

                for result, err in scheduled_callbacks:
                    if ev not in cb:
                        break
                    if err is not None:
                        six.reraise(*err)
                    callback(result)

                if ev.completed and not len(ev.scheduled_callbacks):
                    try:
                        cb.remove(ev)
                    except ValueError:
                        pass

    def _callback_thread(self):
        callbacks = self.__callbacks
        aquire = self.__callback_lock.acquire
        release = self.__callback_lock.release
        event = self.__thread_event
        schedule = self._schedule_thread_callbacks
        trigger = self._kivy_trigger
        target = self.target

        while 1:
            event.wait()
            if self.__signal_exit:
                break
            has_events = False
            aquire()
            keys = callbacks.keys()
            event.clear()
            release()
            for key in keys:
                cb = callbacks[key]
                c = list(cb)
                for ev in c:
                    if not ev.trigger or ev.completed or ev not in cb:
                        continue
                    try:
                        if target is not None:
                            res = getattr(target, key)(**ev.func_kwargs)
                        else:
                            res = getattr(self, key)(**ev.func_kwargs)
                        err = None
                    except Exception:
                        err = sys.exc_info()
                    if ev.repeat:
                        has_events = True
                    if schedule(key, (res, err), c, cb, ev):
                        trigger()
            if has_events:
                event.set()