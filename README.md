# Asnyc. BACpypes

This is a diverging fork of the BACpypes python package.
The goals of development are:

- Removal of asyncore dependecy and the bacpypes.core event loop in favour of asyncio
- Refactored project structure (one class per module where feasible)
- Reduction of multiple inheritance and overall amount of code (for easier maintenance)
- PEP8 compliant code refactoring
- Simplified asynchronous application API

This package will only run at Python 3.6 and above.
