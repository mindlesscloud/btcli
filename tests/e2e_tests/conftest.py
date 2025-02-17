import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import time

import pytest
from async_substrate_interface.async_substrate import AsyncSubstrateInterface

from .utils import setup_wallet


# Fixture for setting up and tearing down a localnet.sh chain between tests
@pytest.fixture(scope="function")
def local_chain(request):
    param = request.param if hasattr(request, "param") else None
    # Get the environment variable for the script path
    script_path = os.getenv("LOCALNET_SH_PATH")

    if not script_path:
        # Skip the test if the localhost.sh path is not set
        logging.warning("LOCALNET_SH_PATH env variable is not set, e2e test skipped.")
        pytest.skip("LOCALNET_SH_PATH environment variable is not set.")

    # Check if param is None, and handle it accordingly
    args = "" if param is None else f"{param}"

    # Compile commands to send to process
    cmds = shlex.split(f"{script_path} {args}")
    # Start new node process
    process = subprocess.Popen(
        cmds, stdout=subprocess.PIPE, text=True, preexec_fn=os.setsid
    )

    # Pattern match indicates node is compiled and ready
    pattern = re.compile(r"Imported #1")

    # Install neuron templates
    logging.info("Downloading and installing neuron templates from github")

    timestamp = int(time.time())

    def wait_for_node_start(process, pattern):
        for line in process.stdout:
            print(line.strip())
            # 20 min as timeout
            if int(time.time()) - timestamp > 20 * 60:
                pytest.fail("Subtensor not started in time")
            if pattern.search(line):
                print("Node started!")
                break

    wait_for_node_start(process, pattern)

    # Run the test, passing in substrate interface
    yield AsyncSubstrateInterface(url="ws://127.0.0.1:9945")

    # Terminate the process group (includes all child processes)
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)

    # Give some time for the process to terminate
    time.sleep(1)

    # If the process is not terminated, send SIGKILL
    if process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)

    # Ensure the process has terminated
    process.wait()


@pytest.fixture(scope="function")
def wallet_setup():
    wallet_paths = []

    def _setup_wallet(uri: str):
        keypair, wallet, wallet_path, exec_command = setup_wallet(uri)
        wallet_paths.append(wallet_path)
        return keypair, wallet, wallet_path, exec_command

    yield _setup_wallet

    # Cleanup after the test
    for path in wallet_paths:
        shutil.rmtree(path, ignore_errors=True)
