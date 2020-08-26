Getting Started
================

Introduction
-------------

PyMoa is a framework for describing and running experiments using local or remote devices.

It is composed of stages that determine the flow of an experiment, devices that interface with arbitrary hardware or
software devices, loggers that automatically log all stage or device state changes, and executors
that can run arbitrary devices on different threads, process, or even remote servers such as on a Raspberry-pi with
minimal code changes.

PyMoa re-uses existing libraries where possible. In particular:

* The **amazing** `trio <https://trio.readthedocs.io/en/stable/>`_ library for all concurrency and event loops
  (running stages, devices, interfacing with threads) and its socket interface (both client and server side).
* `asks <https://asks.readthedocs.io/en/latest/>`_ for making client side requests over the rest api.
* `trio-websocket <https://trio-websocket.readthedocs.io/en/stable/>`_ for making client side requests over
  the websocket api.
* `Quart <https://pgjones.gitlab.io/quart/>`_ and `quart-trio <https://gitlab.com/pgjones/quart-trio/>`_ for the
  server-side rest-api and websockets.
* `Kivy <https://kivy.org/#home>`_ for event and property dispatching in response to data and stage updates.

Framework
---------

The following introduction walks through the basic PyMoa components. `The complete example can be found here
<https://github.com/matham/pymoa/blob/master/examples/intro_example.py>`_.

Stage
*****

PyMoa describes an experiment using hierarchies of :class:`~pymoa.stage.MoaStage` instances.
For example the following experiment

#. Wait for 20 seconds, then repeats the following 2 times;

   #. Waits for a photo-beam to break (by going high),
   #. Releases a sugar pallet (by motor port driven high for 200ms),
   #. Wait for a 20 second - 40 second inter-trial interval
#. Waits for 15 seconds

Can be described in pseudo-code as follows::

    MoaStage:
        Delay:
            delay = 20
        MoaStage:
            repeat = 2
            DigitalGateStage:
                device = photo_bream_device
                exit_state = True
            Delay:
                motor_device.set_channel(True)
                delay = 0.2
            UniformRandomDelay:
                min = 20
                max = 40
        Delay:
            delay = 15

In real code, this experiment structure would be implemented as:

.. code-block:: python3

    class SugarPalletStage(MoaStage):

        async def do_trial(self):
            await self.motor_device.write_state(True)
            await trio.sleep(0.2)
            await self.motor_device.write_state(False)

    root = MoaStage(name='Root stage')
    trial = MoaStage(name='Trial', repeat=2)

    root.add_stage(Delay(delay=20, name='Habituation'))
    root.add_stage(trial)
    root.add_stage(Delay(delay=15, name='post delay'))

    trial.add_stage(DigitalGateStage(
        device=photo_bream_device, exit_state=True, name='photobeam_stage'))
    trial.add_stage(SugarPalletStage(
        motor_device=motor_device, name='sugar pallet stage', delay=0.2))
    trial.add_stage(UniformRandomDelay(min=20, max=40, name='ITI'))

The experiment would then be run using ``await root.run_stage()``, which executes all the stages.

A :class:`~pymoa.stage.MoaStage` will perform an action when each of its trials are run.
The stage will then :attr:`~pymoa.stage.MoaStage.repeat` the stage's action for each trial. Simultaneously, for each trial,
the stage will execute its sub-:attr:`~pymoa.stage.MoaStage.stages` serially or in parallel as specified by
:attr:`~pymoa.stage.MoaStage.order`. :attr:`~pymoa.stage.MoaStage.complete_on` and
:attr:`~pymoa.stage.MoaStage.complete_on_whom` help determine when a trial is complete so it can be repeated again
or complete the stage when the trial :attr:`~pymoa.stage.MoaStage.count` is done.

The action performed by the stage is customized by overwriting (and calling ``super`` within) these methods:
:meth:`~pymoa.stage.MoaStage.init_stage`, :meth:`~pymoa.stage.MoaStage.init_trial`,
:meth:`~pymoa.stage.MoaStage.do_trial`, :meth:`~pymoa.stage.MoaStage.trial_done`,
:meth:`~pymoa.stage.MoaStage.stage_done`. Other methods and events are also available for further customization.

Some example stages are the :class:`~pymoa.stage.delay.Delay` stage that waits for specified delay and the
:class:`~pymoa.stage.gate.GateStage` which waits until the specified device condition is met.


Device
******

The :class:`~pymoa.device.Device` base class is the interface to interact with input/output devices. Generally they
store the current device state as a property of the device (e.g. the state of a digital channel).
Whenever the device is updated, it dispatches the ``on_data_update`` event to signal to listeners that
the device's state was updated.

:mod:`~pymoa.device.port` defines some additional interfaces for channels and channel ports.
:mod:`~pymoa.device.digital` and :mod:`~pymoa.device.analog` provide further interfaces for interacting with digital and
analog devices, respectively. :mod:`~pymoa.device.adc` provides a interface for an ADC device. These interfaces
are example implementations to be customized.

For the above experiment, we create a virtual photobeam sensor and sugar pallet delivering device by implementing
:class:`~pymoa.device.digital.DigitalChannel` as follows:

.. code-block:: python3

    class VirtualDevice(DigitalChannel):

        async def write_state(self, state: bool, **kwargs):
            self.state = state
            self.timestamp = perf_counter()
            self.dispatch('on_data_update', self)

        async def pump_state(self):
            while True:
                await trio.sleep(random.random() * 10 + 1)
                await self.write_state(random.random() >= 0.5)

    photo_bream_device = VirtualDevice(name='photobeam_device')
    motor_device = VirtualDevice(name='motor_device')


``write_state`` simply saves the state and triggers the update. This is simulating setting the channel to high or low
(e.g. turning ON the motor). ``pump_state`` will continuously "read" the channel by randomly generating a high or low
state for the channel.


Logging
*******

Stages and devices support automatic logging of important properties through the :class:`~pymoa.data_logger.Loggable`
interface. The interface provides a way to indicate which properties/events to log and what triggers the logging
action. :class:`~pymoa.stage.MoaStage` and :class:`~pymoa.device.Device` includes this interface by default.

Example loggers are :class:`~pymoa.data_logger.SimpleCSVLogger` and :class:`~pymoa.data_logger.SimpleTerminalLogger`,
which log the data to a csv file and to the terminal, respectively.

For example, to log the experiment stages above, the following will associate the logger with the stages:

.. code-block:: python3

    logger = SimpleTerminalLogger()
    for stage in root.iterate_stages():
        logger.add_logged_instance(stage)

When the experiment is run, this will print the following to the terminal:

.. csv-table:: Printed output
    :file: media/intro_log_output.csv
    :header-rows: 1

Remote Execution
****************

One the best components of this framework is the ability to execute and interface with devices that are remote
to the system running the experiments. PyMoa implements some executor classes that help achieve this very simply.

For example imagine instead of being able to set the state of the device above on our system, we needed to call the
device over the network or in a different process or thread. E.g. this device represented a raspberry-pi so
``write_state`` needs to run on the pi. For the following example we'll use a thread executor, but a socket or rest-api
executor will work similarly.

The device will now be adjusted as follows:

.. code-block:: python3

    class VirtualDevice(DigitalChannel):

        def executor_callback(self, return_value):
            self.state, self.timestamp = return_value
            self.dispatch('on_data_update', self)

        @apply_executor(callback=executor_callback)
        def write_state(self, state: bool, **kwargs):
            return state, perf_counter()

    executor = ThreadExecutor()
    photo_bream_device = VirtualDevice(name='photobeam_device', executor=executor)
    motor_device = VirtualDevice(name='motor_device', executor=executor)

With this simple change, when we call it as follows ``await motor_device.write_state(True)``, ``write_state`` will be
executed in a second thread and the result will be returned to us. In addition, the result will be passed to the
callback provided in the decorator to apply the result generically as needed.

Executing on e.g. a raspberry-pi is just as simple: instantiate the :mod:`~pymoa.executor.remote.app.quart` server
on the raspberry-pi. This will launch a server that can be communicated with using a nice rest api as well as more
efficient websockets. And from the the client side, you'd simply do
``executor = WebSocketExecutor(server='x.y.z.a', port=5000)`` and everything else will mostly work the same as the threading
example above. The only difference is that we'd also need to call ``await executor.ensure_remote_instance(motor_device)``
to create the device on the pi, but afterwards calling ``await motor_device.write_state(True)`` will execute the
``write_state`` on the pi and return the result to the client!!!

Remote clock
^^^^^^^^^^^^

Executors also support pinging the executor to return the current server time. By running this periodically we can
estimate the lag to executing on the server, but more importantly, we can also align the server timestamped events
to the local clock by doing a simple linear regression.

Performance
^^^^^^^^^^^^

Following is some basic performance data for the various implemented executors. The last two rows are when running
on a server on the Raspberry-pi over WiFi:

.. csv-table:: Performance data
    :header-rows: 1

    Executor,Round-trip lag,Execution Rate,Continuous Execution rate
    RestExecutor,8.68ms,95.36Hz,1495.93Hz
    WebSocketExecutor,2.20ms,533.46Hz,1104.19Hz
    MultiprocessSocketExecutor,0.48ms,1132.06Hz,3144.60Hz
    ThreadExecutor,0.45ms,2789.56Hz,5395.46Hz
    AsyncThreadExecutor,1.16ms,-,-
    DummyRemoteExecutor,0.07ms,10327.27Hz,5739.54Hz
    none,-,246669.96Hz,10018.94Hz
    RPi-RestExecutor,16.56ms,59.52Hz,847.97Hz
    RPi-WebSocketExecutor,6.14ms,153.43Hz,377.19Hz

Running the experiment
**********************

Once the above has been defined, to run the experiment simply schedule the async functions to run in trio's event loop.
This eventloop will do two things simultaneously; continuously "read" the photo beam device to see when the photobeam
is "broken" and execute the experiment's stages:

.. code-block:: python3

    async def run_experiment():
        # start the threading executor
        await executor.start_executor()
        async with trio.open_nursery() as nursery:
            async def run_root_stage():
                # run the experiment stages, but when done also cancel reading the devices
                await root.run_stage()
                nursery.cancel_scope.cancel()

            # reads the photobeam device continuously
            nursery.start_soon(photo_bream_device.pump_state)
            # runs the experiment stages
            nursery.start_soon(run_root_stage)

        # we're done so we can stop the threading executor
        await executor.stop_executor()

    trio.run(run_experiment)
