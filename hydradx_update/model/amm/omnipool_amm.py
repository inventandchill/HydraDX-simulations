import copy
import math
import string


def asset_invariant(state: dict, i: int) -> float:
    """Invariant for specific asset"""
    return state['R'][i] * state['Q'][i]


def swap_hdx_delta_Qi(old_state: dict, delta_Ri: float, i: int) -> float:
    return old_state['Q'][i] * (- delta_Ri / (old_state['R'][i] + delta_Ri))


def swap_hdx_delta_Ri(old_state: dict, delta_Qi: float, i: int) -> float:
    return old_state['R'][i] * (- delta_Qi / (old_state['Q'][i] + delta_Qi))


def weight_i(state: dict, i: int) -> float:
    return state['Q'][i] / sum(state['Q'])


def price_i(state: dict, i: int) -> float:
    """Price of i denominated in HDX"""
    if state['R'][i] == 0:
        return 0
    else:
        return state['Q'][i] / state['R'][i]


def initialize_pool_state(init_d=None) -> dict:
    if init_d is None:
        init_d = {}
    state = {
        'R': [],
        'Q': [],
        'S': [],
        'B': []
    }
    for i in range(len(init_d['R'])):
        state = add_asset(state, init_d['R'][i], init_d['P'][i])
    return state


def add_asset(old_state: dict, init_R: float, price: float) -> dict:
    new_state = copy.deepcopy(old_state)
    new_state['R'].append(init_R)
    new_state['Q'].append(price * init_R)
    new_state['S'].append(init_R)
    new_state['B'].append(init_R)
    return new_state


def swap_hdx(
        old_state: dict,
        old_agents: dict,
        trader_id: string,
        delta_R: float,
        delta_Q: float,
        i: int
) -> tuple:
    """Compute new state after HDX swap"""

    new_state = copy.deepcopy(old_state)
    new_agents = copy.deepcopy(old_agents)
    if delta_Q == 0:
        delta_Q = swap_hdx_delta_Qi(old_state, delta_R, i)
    elif delta_R == 0:
        delta_R = swap_hdx_delta_Ri(old_state, delta_Q, i)
    else:
        raise Exception

    # Token amounts update
    new_state['R'][i] += delta_R
    new_state['Q'][i] += delta_Q
    new_agents[trader_id]['r'][i] -= delta_R
    new_agents[trader_id]['q'] -= delta_Q

    return new_state, new_agents


def swap_assets(
        old_state: dict,
        old_agents: dict,
        trader_id: string,
        delta_sell: float,
        i_buy: int,
        i_sell: int
) -> tuple:
    # swap asset in for HDX
    first_state, first_agents = swap_hdx(old_state, old_agents, trader_id, delta_sell, 0, i_sell)
    # swap HDX in for asset
    delta_Q = first_agents[trader_id]['q'] - old_agents[trader_id]['q']
    return swap_hdx(first_state, first_agents, trader_id, 0, delta_Q, i_buy)


def add_risk_liquidity(
        old_state: dict,
        old_agents: dict,
        LP_id: string,
        delta_R: float,
        i: int
) -> tuple:
    """Compute new state after liquidity addition"""

    assert delta_R > 0, "delta_R must be positive: " + str(delta_R)
    assert i >= 0, "invalid value for i: " + str(i)

    new_state = copy.deepcopy(old_state)
    new_agents = copy.deepcopy(old_agents)

    # Token amounts update
    new_state['R'][i] += delta_R
    new_agents[LP_id]['r'][i] -= delta_R

    # Share update
    new_state['S'][i] *= new_state['R'][i] / old_state['R'][i]
    new_agents[LP_id]['s'][i] += new_state['S'][i] - old_state['S'][i]

    # HDX add
    delta_Q = old_state['P'][i] * delta_R
    new_state['Q'][i] += delta_Q

    # set price at which liquidity was added
    new_agents[LP_id]['p'][i] = price_i(new_state, i)

    return new_state, new_agents


def remove_risk_liquidity(
        old_state: dict,
        old_agents: dict,
        LP_id: string,
        delta_S: float,
        i: int
) -> tuple:
    """Compute new state after liquidity removal"""
    assert delta_S <= 0, "delta_S cannot be positive: " + str(delta_S)
    assert i >= 0, "invalid value for i: " + str(i)

    new_state = copy.deepcopy(old_state)
    new_agents = copy.deepcopy(old_agents)

    piq = price_i(old_state, i)
    p0 = new_agents[LP_id]['p'][i]
    mult = 2 * piq / (piq + p0) * math.sqrt(piq / p0)

    # Share update
    delta_B = max((mult - 1) * delta_S, - old_state['B'][i])
    new_state['B'][i] += delta_B
    new_state['S'][i] += delta_S + delta_B
    new_agents[LP_id]['s'][i] += delta_S

    # Token amounts update
    delta_R = old_state['R'][i] * max((delta_S + delta_B) / old_state['S'][i], -1)
    new_state['R'][i] += delta_R
    new_agents[LP_id]['r'][i] -= delta_R
    if piq >= p0:  # prevents rounding errors
        new_agents[LP_id]['q'] -= price_i(old_state, i) * (
                mult * delta_S / old_state['S'][i] * old_state['R'][i] - delta_R)

    # HDX burn
    delta_Q = old_state['P'][i] * delta_R
    new_state['Q'][i] += delta_Q

    return new_state, new_agents