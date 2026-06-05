# SPDX-FileCopyrightText: 2021 Sebastian Garcia <sebastian.garcia@agents.fel.cvut.cz>
# SPDX-License-Identifier: GPL-2.0-only
import asyncio
from unittest.mock import Mock

import pytest

from tests.module_factory import ModuleFactory


@pytest.mark.parametrize(
    "exception",
    [KeyboardInterrupt(), SystemExit(), asyncio.CancelledError()],
)
def test_handle_task_exception_ignores_shutdown_exceptions(exception):
    """
    Verify shutdown exceptions are not logged as task failures.

    :param exception: Shutdown exception raised or returned by a task.
    :return: None.
    """
    module_factory = ModuleFactory()
    flowalerts = module_factory.create_flowalerts_obj()
    task = Mock()
    task.exception.return_value = exception

    flowalerts.handle_task_exception(task)

    flowalerts.print.assert_not_called()


def test_handle_task_exception_ignores_cancelled_tasks():
    """
    Verify cancelled tasks are not logged as task failures.

    :return: None.
    """
    module_factory = ModuleFactory()
    flowalerts = module_factory.create_flowalerts_obj()
    task = Mock()
    task.exception.side_effect = asyncio.CancelledError()

    flowalerts.handle_task_exception(task)

    flowalerts.print.assert_not_called()


def test_handle_task_exception_logs_regular_exceptions():
    """
    Verify non-shutdown task exceptions are still logged.

    :return: None.
    """
    module_factory = ModuleFactory()
    flowalerts = module_factory.create_flowalerts_obj()
    exception = ValueError("boom")
    task = Mock()
    task.exception.return_value = exception
    flowalerts.print_traceback_from_exception = Mock()

    flowalerts.handle_task_exception(task)

    flowalerts.print.assert_called_once_with(
        "Unhandled exception in task: ValueError('boom') .. "
    )
    flowalerts.print_traceback_from_exception.assert_called_once_with(
        exception, task
    )
