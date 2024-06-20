from typing import Any, cast

import uvicorn
from communex.balance import from_nano, from_horus
from communex.client import CommuneClient
from communex.misc import get_map_modules, get_map_subnets_params
from fastapi import FastAPI
from math import ceil

app = FastAPI()

node_url = "wss://commune-api-node-2.communeai.net"


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/subnets")
def read_root():
    client = CommuneClient(node_url)

    subnets = get_map_subnets_params(client)
    keys, values = subnets.keys(), subnets.values()
    subnets_with_netuids = [
        {"netuid": key, **value} for key, value in zip(keys, values)
    ]

    subnet_stakes = client.query_map_total_stake()
    subnets_with_stakes = [
        {"stake": from_nano(subnet_stakes.get(netuid, 0))} for netuid in keys
    ]
    subnets_with_stakes = [
        {**subnets_with_netuids[i], **subnets_with_stakes[i]} for i in range(len(keys))
    ]

    subnets_with_netuids = sorted(
        subnets_with_stakes, key=lambda x: x["emission"], reverse=True)

    for subnet_dict in subnets_with_netuids:
        bonds = subnet_dict["bonds_ma"]
        if bonds:
            subnet_dict["bonds_ma"] = str(
                from_nano(subnet_dict["bonds_ma"])) + " J"

    return {"subnets": subnets_with_netuids}


@app.get("/apr")
def read_validating_apr():
    client = CommuneClient(node_url)

    # network parameters
    block_time = 8  # seconds
    seconds_in_a_day = 86400
    blocks_in_a_day = seconds_in_a_day / block_time

    unit_emission = client.get_unit_emission()
    map_query = client.query_batch_map(
        {
            "SubspaceModule": [
                ("TotalStake", []),
            ]
        }
    )

    standard_query = client.query_batch(
        {
            "SubspaceModule": [
                ("FloorDelegationFee", []),
                ("FloorFounderShare", []),
            ]
        }
    )

    staked = map_query["TotalStake"]
    delegation_fee = standard_query["FloorDelegationFee"]
    founder_fee = standard_query["FloorFounderShare"]
    fee = delegation_fee + founder_fee
    fee_to_float = fee / 100

    total_staked_tokens = from_nano(sum(staked.values()))

    # 50% of the total emission goes to stakers
    daily_token_rewards = blocks_in_a_day * from_nano(unit_emission) / 2
    _apr = (daily_token_rewards * (1 - fee_to_float)
            * 365) / total_staked_tokens * 100

    return {"apr": ceil(_apr)}


@app.get("/daily-emission")
def read_daily_emission():
    client = CommuneClient(node_url)

    emission = client.get_unit_emission()
    daily_emission_raw = from_nano(emission * 10_800)  # blocks in a day
    return {"daily_emission": ceil(daily_emission_raw)}


@app.get("/subnets/{netuid}/modules")
def read_item(netuid: int):
    client = CommuneClient(node_url)

    modules_map = get_map_modules(client, netuid=netuid)
    modules_to_list = [value for _, value in modules_map.items()]

    immunity_period = client.get_immunity_period(netuid)
    tempo = client.get_tempo(netuid)

    last_block = client.get_block()["header"]["number"]

    to_exclude = ["stake_from", "metadata", "last_update", "regblock"]
    modules = transform_module_into(
        to_exclude, last_block, immunity_period, modules_to_list, tempo)

    return {"modules": modules}


def transform_module_into(
    to_exclude: list[str], last_block: int,
    immunity_period: int, modules: list[Any],
    tempo: int
) -> list[Any]:
    mods = cast(list[dict[str, Any]], modules)
    transformed_modules: list[dict[str, Any]] = []
    for mod in mods:
        module = mod.copy()
        module_regblock = module["regblock"]
        module["in_immunity"] = module_regblock + immunity_period > last_block

        for key in to_exclude:
            del module[key]
        module["stake"] = round(from_nano(module["stake"]), 2)
        module["emission"] = round(
            from_horus(
                module["emission"], tempo
            ),
            4
        )

        # add type
        module_type = 'validator'
        if module["incentive"] == module["dividends"] == 0:
            module_type = "inactive"
        elif module["incentive"] > module["dividends"]:
            module_type = "miner"
        module["type"] = module_type

        transformed_modules.append(module)

    return transformed_modules


if __name__ == "__main__":
    uvicorn.run(app=app, host="0.0.0.0", port=7860)
