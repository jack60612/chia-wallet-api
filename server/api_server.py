"""   
    Copyright 2022 Jack Nelson

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

# Other imports
from chia.util.bech32m import decode_puzzle_hash
from chia.util.byte_types import hexstr_to_bytes
from sanic.log import logger
import os
import yaml
from typing import List, Optional, Tuple, Dict, Union
from sanic import Sanic, Request, HTTPResponse, text

# Chia imports
from chia.util.json_util import dict_to_json_str
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.consensus.constants import ConsensusConstants
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.config import load_config
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.ints import uint8, uint64, uint32, uint16
from chia.types.blockchain_format.coin import Coin
from chia.types.coin_record import CoinRecord
from chia.types.coin_spend import CoinSpend
from chia.types.spend_bundle import SpendBundle

from server.api import ApiApp

app = Sanic("Jacks-Node-Api")


def sanic_jsonify(response) -> HTTPResponse:
    return HTTPResponse(
        body=dict_to_json_str(response), content_type="application/json"
    )


class ApiServer:
    def __init__(self, config: Dict, constants: ConsensusConstants):
        with open(os.getcwd() + "/config.yaml") as f:
            self.config_file: Dict = yaml.safe_load(f)

        # start logging
        self.log = logger

        # initialize ApiApp
        self.ApiApp = ApiApp(config, constants, self.config_file, self.log)

        # load config.
        self.host = self.config_file["server_host"]
        self.port = int(self.config_file["server_port"])

    async def start(self):
        await self.ApiApp.start()

    async def stop(self):
        await self.ApiApp.stop()

    @staticmethod
    async def index(_) -> HTTPResponse:
        return text("A Chia Node API Server")

    async def peak(self, request_obj: Request) -> HTTPResponse:
        return sanic_jsonify(
            {
                "peak": await self.ApiApp.get_current_height(),
                "synced": self.ApiApp.blockchain_state["sync"]["synced"],
            }
        )

    async def blockchain_state(self, request_obj: Request) -> HTTPResponse:
        return sanic_jsonify(self.ApiApp.blockchain_state)

    async def get_coinrecords_from_ph(self, request_obj: Request) -> HTTPResponse:
        request = request_obj.args.getlist("ph")
        try:
            puzzle_hashes = [hexstr_to_bytes(r) for r in request]
        except ValueError as e:
            self.log.info(f"Non hex value entered for get_balance: {e}")
            return sanic_jsonify({"error": "ValueError"})
        if puzzle_hashes is None:
            return sanic_jsonify(None)
        return sanic_jsonify(
            await self.ApiApp.get_coin_records_for_puzzle_hashes(puzzle_hashes)
        )

    async def get_balance(self, request_obj: Request) -> HTTPResponse:
        mojo_total = 0
        request = request_obj.args.getlist("wallet")
        if request is None:
            return sanic_jsonify({"error": "Missing Arguments"})
        try:
            puzzle_hash = [decode_puzzle_hash(request)]
        except ValueError as e:
            self.log.info(f"Non hex value entered for get_balance: {e}")
            return sanic_jsonify({"error": "ValueError"})
        if puzzle_hash is None:
            return sanic_jsonify(None)
        coin_records = await self.ApiApp.get_coin_records_for_puzzle_hashes(puzzle_hash)

        for coin_record in coin_records:
            mojo_total += coin_record.coin.amount
        return sanic_jsonify({"mojo": mojo_total})

    async def submit_spend_bundle(
        self, request_obj: Request
    ) -> HTTPResponse:  # post request
        spend_bundle: SpendBundle = SpendBundle.from_json_dict(request_obj.json)
        return sanic_jsonify(await self.ApiApp.submit_signed_spend_bundle(spend_bundle))

    async def get_mempool_tx(
        self, request_obj: Request
    ) -> HTTPResponse:  # get transactions in mempool from the tx_id.
        request = request_obj.args.get("tx_id")
        if request is None:
            return sanic_jsonify(None)
        try:
            transaction_id = hexstr_to_bytes(request)
        except ValueError as e:
            self.log.info(f"Non hex value entered for get_mempool_tx: {e}")
            return sanic_jsonify({"error": "ValueError"})
        return sanic_jsonify(await self.ApiApp.get_mempool_transaction(transaction_id))

    async def get_coin_by_id(
        self, request_obj: Request
    ) -> HTTPResponse:  # get coin record by the coins ID.
        request = request_obj.args.get("coin_id")
        if request is None:
            return sanic_jsonify(None)
        try:
            coin_id = hexstr_to_bytes(request)
        except ValueError as e:
            self.log.info(f"Non hex value entered for get_mempool_tx: {e}")
            return sanic_jsonify({"error": "ValueError"})
        return sanic_jsonify(await self.ApiApp.get_coin_record_by_id(coin_id))


server: ApiServer


def start_api_server():
    global server
    # load chia config and constants
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    overrides = config["network_overrides"]["constants"][config["selected_network"]]
    constants: ConsensusConstants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)
    # initialize ApiServer
    server = ApiServer(config, constants)
    # add routes
    app.add_route(server.index, "/")
    app.add_route(server.peak, "/peak")
    app.add_route(server.blockchain_state, "/blockchain_state")
    app.add_route(server.get_coinrecords_from_ph, "/get_coinrecords")
    app.add_route(server.get_balance, "/get_balance")
    app.add_route(server.submit_spend_bundle, "/submit_bundle", methods=["POST"])
    app.add_route(server.get_mempool_tx, "/mempool_tx")
    app.add_route(server.get_coin_by_id, "/coin_id")
    # start app
    app.run(
        host=server.host,
        port=server.port,
        workers=1,
        access_log=False,
        debug=True,
    )


@app.before_server_start
async def start(app, loop):
    await server.start()


@app.after_server_stop
async def stop(app, loop):
    await server.stop()


def main():
    try:
        start_api_server()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
