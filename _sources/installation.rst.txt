.. _install-pymoa:

*************
Installation
*************

Dependencies
-------------

* Python 3.7+
* Kivy Master `E.g. Windows nightly wheels <https://kivy.org/docs/installation/installation-windows.html#nightly-wheel-installation>`_

Installing PyMoa
---------------------
After installing the dependencies, pymoa can be installed using::

    pip install pymoa[network]

to get the last release from pypi, or to get pymoa master for the most current pymoa version do::

    pip install https://github.com/matham/pymoa/archive/master.zip --install-option="--extras-require=network"

This installs all the network dependencies required when pymoa will use remote devices.
