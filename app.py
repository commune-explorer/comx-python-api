from typing import Any, cast

import uvicorn
from communex.balance import from_nano, from_horus
from communex.client import CommuneClient
from communex.misc import get_map_modules, get_map_subnets_params
from fastapi import FastAPI

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

    subnets_with_netuids = sorted(subnets_with_stakes, key=lambda x: x["emission"], reverse=True)

    for subnet_dict in subnets_with_netuids:
        bonds = subnet_dict["bonds_ma"]
        if bonds:
            subnet_dict["bonds_ma"] = str(from_nano(subnet_dict["bonds_ma"])) + " J"

    return {"subnets": subnets_with_netuids}


@app.get("/subnets/{netuid}/modules")
def read_item(netuid: int):
    client = CommuneClient(node_url)

    modules_map = get_map_modules(client, netuid=netuid)
    modules_to_list = [value for _, value in modules_map.items()]

    immunity_period = client.get_immunity_period(netuid)
    last_block = client.get_block()["header"]["number"]

    modules: list[Any] = []

    for mod in modules_to_list:
        module = cast(Any, mod.copy())

        module["in_immunity"] = module["regblock"] + immunity_period > last_block
        module["stake"] = round(from_nano(module["stake"]), 2)
        module["emission"] = round(from_horus(module["emission"]), 4)

        # add type
        module_type = 'validator'
        if module["incentive"] == module["dividends"] == 0:
            module_type = "inactive"
        elif module["incentive"] > module["dividends"]:
            module_type = "miner"
        module["type"] = module_type

        # exclude
        to_exclude = ["stake_from", "metadata", "last_update", "regblock"]
        for key in to_exclude:
            del module[key]

        modules.append(module)

    return {"modules": modules}


if __name__ == "__main__":
    uvicorn.run(app=app, host="0.0.0.0", port=7860)
