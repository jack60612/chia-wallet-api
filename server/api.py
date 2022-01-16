# Standard python imports
import asyncio
from logging import Logger
from typing import List, Optional, Tuple, Dict, Union

# chia imports
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.consensus.constants import ConsensusConstants
from chia.util.ints import uint8, uint64, uint32, uint16
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.types.blockchain_format.coin import Coin
from chia.types.coin_record import CoinRecord
from chia.types.coin_spend import CoinSpend
from chia.types.spend_bundle import SpendBundle


class ApiApp:
    def __init__(
        self,
        config: Dict,
        constants: ConsensusConstants,
        config_file: Dict,
        log: Logger,
    ):
        # define passed through logger
        self.logger = log
        # load chia config and constants
        self.config = config
        self.constants = constants

        # load hostname and port of the node from the config file or default to chia config file
        self.hostname = config_file.get(
            "node_rpc_hostname", self.config["self_hostname"]
        )
        self.port: uint16 = uint16(config_file.get("node_rpc_port", 8555))
        self.scan_start_height: uint32 = uint32(config_file.get("start_height", 0))
        # initialize state
        self.blockchain_state: Dict = {}

        # define tasks and the Node rpc connection.
        self.node_rpc_client: Optional[FullNodeRpcClient] = None
        self.get_peak_loop_task: Optional[asyncio.Task] = None

    async def start(self):
        # start rpc node connection
        self.node_rpc_client = await FullNodeRpcClient.create(
            self.hostname, self.port, DEFAULT_ROOT_PATH, self.config
        )
        self.blockchain_state = await self.node_rpc_client.get_blockchain_state()
        self.logger.info(f"Connected to node at {self.hostname}:{self.port}")
        # start tasks
        self.get_peak_loop_task = asyncio.create_task(self.get_peak_loop())

    async def stop(self):
        if self.get_peak_loop_task is not None:
            self.get_peak_loop_task.cancel()
        # stop node
        self.node_rpc_client.close()
        await self.node_rpc_client.await_closed()

    async def check_sync(self):
        if not self.blockchain_state["sync"]["synced"]:
            self.logger.error("Not synced")
            return False
        else:
            return True

    async def get_peak_loop(self):
        """
        Periodically contacts the full node to get the latest state of the blockchain
        """
        while True:
            try:
                self.blockchain_state = (
                    await self.node_rpc_client.get_blockchain_state()
                )
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.logger.info("Cancelled get_peak_loop, closing")
                return
            except Exception as e:
                self.logger.error(f"Unexpected error in get_peak_loop: {e}")
                await asyncio.sleep(30)

    # returns current blockchain peak
    async def get_current_height(self) -> Optional[int]:
        return self.blockchain_state["peak"].height

    async def get_coin_records_for_puzzle_hashes(
        self, puzzle_hashes: List[bytes32], include_spent: bool = False
    ) -> Optional[List[CoinRecord]]:
        if not self.check_sync:
            return
        coin_records: List[
            CoinRecord
        ] = await self.node_rpc_client.get_coin_records_by_puzzle_hashes(
            puzzle_hashes,
            include_spent_coins=include_spent,
            start_height=self.scan_start_height,
        )
        return coin_records

    async def submit_signed_spend_bundle(
        self, spend_bundle: SpendBundle
    ) -> Optional[int]:
        if not self.blockchain_state["sync"]["synced"]:
            self.logger.error("Not synced")
            return
        # TODO: we probably need to add additional checks before submitting to mempool in the future
        return await self.node_rpc_client.push_tx(spend_bundle)

    async def get_mempool_transaction(self, transaction_id: bytes32):
        if not self.blockchain_state["sync"]["synced"]:
            self.logger.error("Not synced")
            return
        return await self.node_rpc_client.get_mempool_item_by_tx_id(transaction_id)

    async def get_coin_record_by_id(self, coin_id: bytes32) -> Optional[CoinRecord]:
        if not self.blockchain_state["sync"]["synced"]:
            self.logger.error("Not synced")
            return
        return await self.node_rpc_client.get_coin_record_by_name(coin_id)
