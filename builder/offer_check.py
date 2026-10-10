"""Generated code for the offer steps: per-product facts, offer check, promise values.

All brief rules arrive as spec data (``offer`` section) and are embedded in the
snippets as JSON. The snippets read and write only ``vars``, never raise, and contain
no double braces.
"""

from __future__ import annotations

import json
from typing import Any

from .prompts import OFFER_VERDICT_MESSAGES
from .spec import PhoneAgentSpec

# Workflow variables owned by the offer steps (framework names, not brief data).
OFFER_DATE = "offer_date"
OFFER_AMOUNT = "offer_amount"
OFFER_PRODUCT = "offer_product_number"
OFFER_PROGRESS = "offer_progress"
OFFERS_ACCEPTED = "offers_accepted"
OFFERS_ACCEPTED_COUNT = "offers_accepted_count"


def _py_literal(value: Any) -> str:
    """A Python expression that rebuilds ``value`` from JSON without any brace characters."""
    text = json.dumps(json.dumps(value, sort_keys=True))
    return "json.loads(" + text.replace("{", "\\u007b").replace("}", "\\u007d") + ")"


def _verdict_messages() -> dict[str, str]:
    messages = {}
    for line in OFFER_VERDICT_MESSAGES.text.splitlines():
        key, _, sentence = line.partition(": ")
        messages[key.strip()] = sentence.strip()
    return messages


def _config(spec: PhoneAgentSpec, reset_variables: list[str]) -> dict[str, Any]:
    offer = spec.offer.data
    return {
        "offer": {key: value for key, value in offer.items() if key != "rules"},
        "products_variable": spec.account.data["products_variable"],
        "products_flat": "get_account_response.data." + spec.account.data["products_field"],
        "product_id_field": spec.account.data["product_id_field"],
        "expected_variable": spec.confirmation.data["expected_count_variable"],
        "reset": reset_variables,
        "messages": _verdict_messages(),
    }


PRELUDE = """import datetime
import json
import re
CONFIG = __CONFIG__
OFFER = CONFIG['offer']
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def as_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = []
    return value if isinstance(value, list) else []


def load_products():
    products = as_list(vars.get(CONFIG['products_variable']))
    if not products:
        products = as_list(vars.get(CONFIG['products_flat']))
    return [item for item in products if isinstance(item, dict)]


def parse_day(value):
    text = str(value or '').strip()
    match = re.search(r'(\\d{4})-(\\d{1,2})-(\\d{1,2})', text)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except Exception:
        return None


def parse_amount(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r'[^0-9.,]', '', str(value or ''))
    if text.count(',') and not text.count('.'):
        text = text.replace(',', '.')
    text = text.replace(',', '')
    try:
        return float(text)
    except Exception:
        return None


def today():
    day = parse_day(vars.get(OFFER['today_variable']))
    return day or datetime.date.today()


def is_business(day):
    return day.isoweekday() not in OFFER['non_business_weekdays'] and day.isoformat() not in OFFER['holidays']


def shift_to_business(day, step):
    for _ in range(400):
        if is_business(day):
            return day
        day = day + datetime.timedelta(days=step)
    return day


def add_days(start, rule):
    days = int(rule.get('days') or 0)
    if rule.get('unit') == 'business':
        day = start
        counted = 0
        for _ in range(4000):
            if counted >= days:
                break
            day = day + datetime.timedelta(days=1)
            if is_business(day):
                counted += 1
        return day
    return start + datetime.timedelta(days=days)


def matches(product, conditions):
    for condition in conditions or []:
        value = product.get(condition.get('field'))
        if 'equals' in condition and str(value) != str(condition['equals']):
            return False
        if 'in' in condition and str(value) not in [str(item) for item in condition['in']]:
            return False
        for key in ('min', 'max'):
            if key in condition:
                number = parse_amount(value)
                if number is None:
                    return False
                if key == 'min' and number < float(condition[key]):
                    return False
                if key == 'max' and number > float(condition[key]):
                    return False
    return True


def first_rule(product, rules):
    for rule in rules or []:
        if matches(product, rule.get('when')):
            return rule
    return None


def amount_limit(product, rules):
    rule = first_rule(product, rules)
    if rule is None:
        return None
    if 'value' in rule:
        base = parse_amount(rule['value'])
    else:
        base = parse_amount(product.get(rule.get('field')))
    if base is None:
        return None
    return round(base * float(rule.get('share', 1)), 2)


def limits(product):
    start = today()
    earliest = add_days(start, OFFER['earliest'])
    if OFFER['promise_date_must_be_business_day']:
        earliest = shift_to_business(earliest, 1)
    latest = None
    rule = first_rule(product, OFFER['latest'])
    if rule is not None:
        latest = add_days(start, rule)
        if rule.get('unit') != 'business' and OFFER['latest_on_non_business_day'] != 'keep':
            latest = shift_to_business(latest, -1 if OFFER['latest_on_non_business_day'] == 'previous' else 1)
    return earliest, latest, amount_limit(product, OFFER['min_amount']), amount_limit(product, OFFER['max_amount'])


def say_day(day):
    return WEEKDAYS[day.weekday()] + ' ' + day.isoformat() if day else 'none'


def say_amount(amount):
    return ('%.2f' % amount) if amount is not None else 'none'


def product_facts(index, product):
    earliest, latest, low, high = limits(product)
    shown = ', '.join(
        str(key) + ' ' + str(value) for key, value in product.items()
        if key != CONFIG['product_id_field'] and not isinstance(value, (dict, list))
    )
    return (
        'Product ' + str(index) + ': ' + shown + '. Earliest date ' + say_day(earliest)
        + '; latest date ' + say_day(latest) + '; minimum amount ' + say_amount(low)
        + '; maximum amount ' + say_amount(high) + '.'
    )


def accepted_offers():
    value = vars.get(CONFIG['accepted'])
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    return value if isinstance(value, dict) else dict()


def summary(accepted):
    lines = []
    for key in sorted(accepted, key=lambda item: int(item) if str(item).isdigit() else 0):
        entry = accepted[key]
        lines.append('Product ' + str(key) + ': ' + say_amount(parse_amount(entry.get('amount'))) + ' on ' + say_day(parse_day(entry.get('date'))))
    return '; '.join(lines) or 'none'
"""


SETUP_BODY = """try:
    lines = [product_facts(index, product) for index, product in enumerate(load_products(), start=1)]
    vars['products_facts'] = ' '.join(lines) or 'No products were returned.'
    vars['today_text'] = say_day(today())
except Exception:
    vars['products_facts'] = 'No product facts are available.'
    vars['today_text'] = 'unknown'
vars[CONFIG['accepted']] = json.dumps(dict())
vars[CONFIG['accepted_count']] = 0
vars['offers_summary'] = 'none'
vars['offer_message'] = 'No offer has been checked yet.'
vars['offer_verdict'] = 'none'
vars['offer_rejections'] = 0
vars['offer_last_signature'] = ''
vars[CONFIG['progress']] = 'none'
"""


CHECK_BODY = """verdict = 'missing'
suggest_day = None
suggest_amount = None
number = None
progress = 'rejected'
try:
    products = load_products()
    raw_number = vars.get(CONFIG['product_var'])
    try:
        number = int(str(raw_number).strip())
    except Exception:
        number = 1 if len(products) == 1 else None
    day = parse_day(vars.get(CONFIG['date_var']))
    amount = parse_amount(vars.get(CONFIG['amount_var']))
    if number is None or not (1 <= number <= len(products)):
        verdict = 'product_unknown'
    elif day is None or amount is None or amount <= 0:
        verdict = 'missing'
    else:
        product = products[number - 1]
        earliest, latest, low, high = limits(product)
        if day < earliest:
            verdict = 'date_too_early'
            suggest_day = earliest
        elif latest is not None and day > latest:
            verdict = 'date_too_late'
            suggest_day = latest
        elif OFFER['promise_date_must_be_business_day'] and not is_business(day):
            verdict = 'date_not_business_day'
            suggest_day = shift_to_business(day, 1)
            if latest is not None and suggest_day > latest:
                suggest_day = latest
        elif low is not None and amount < low - 0.005:
            verdict = 'amount_too_low'
            suggest_amount = low
        elif high is not None and amount > high + 0.005:
            verdict = 'amount_too_high'
            suggest_amount = high
        else:
            verdict = 'ok'
            accepted = accepted_offers()
            accepted[str(number)] = dict(
                product_id=product.get(CONFIG['product_id_field']), date=day.isoformat(), amount=round(amount, 2)
            )
            vars[CONFIG['accepted']] = json.dumps(accepted)
            vars[CONFIG['accepted_count']] = len(accepted)
            vars['offers_summary'] = summary(accepted)
            try:
                expected = int(vars.get(CONFIG['expected_variable']) or 1)
            except Exception:
                expected = 1
            expected = max(1, min(expected, len(products)))
            progress = 'ready' if len(accepted) >= expected else 'more'
    signature = str(number) + '|' + str(vars.get(CONFIG['date_var'])) + '|' + str(vars.get(CONFIG['amount_var']))
    if verdict not in ('ok', 'missing', 'product_unknown'):
        try:
            rejections = int(vars.get('offer_rejections') or 0)
        except Exception:
            rejections = 0
        if signature != str(vars.get('offer_last_signature') or ''):
            rejections += 1
        vars['offer_rejections'] = rejections
        if rejections >= int(OFFER['max_rejected_offers']):
            progress = 'limit'
    vars['offer_last_signature'] = signature
except Exception:
    verdict = 'missing'
    progress = 'rejected'
message = CONFIG['messages'].get(verdict, CONFIG['messages'].get('missing', ''))
message = message.replace('[date]', say_day(suggest_day)).replace('[amount]', say_amount(suggest_amount))
message = message.replace('[product]', str(number) if number is not None else 'unknown')
if progress == 'more':
    message = message + ' ' + CONFIG['messages'].get('more', '')
vars['offer_verdict'] = verdict
vars['offer_message'] = message
vars['offer_suggested_date'] = suggest_day.isoformat() if suggest_day else ''
vars['offer_suggested_amount'] = suggest_amount if suggest_amount is not None else ''
vars[CONFIG['progress']] = progress
vars[CONFIG['date_var']] = ''
vars[CONFIG['amount_var']] = ''
for name in CONFIG['reset']:
    vars[name] = ''
"""


PROMISE_HOOK_BODY = """try:
    body = config.get('body')
    accepted = accepted_offers()
    if isinstance(body, dict) and accepted:
        choice = body.get(CONFIG['number_field'])
        try:
            key = str(int(str(choice).strip()))
        except Exception:
            key = ''
        if key not in accepted and len(accepted) == 1:
            key = list(accepted)[0]
        entry = accepted.get(key)
        if isinstance(entry, dict):
            body.pop(CONFIG['number_field'], None)
            body[CONFIG['id_field']] = entry.get('product_id')
            body[CONFIG['date_field']] = entry.get('date')
            body[CONFIG['amount_field']] = entry.get('amount')
except Exception:
    pass
"""


def _full_config(spec: PhoneAgentSpec, reset_variables: list[str]) -> dict[str, Any]:
    config = _config(spec, reset_variables)
    config.update({
        "accepted": OFFERS_ACCEPTED, "accepted_count": OFFERS_ACCEPTED_COUNT,
        "progress": OFFER_PROGRESS, "product_var": OFFER_PRODUCT, "date_var": OFFER_DATE,
        "amount_var": OFFER_AMOUNT,
        "number_field": spec.confirmation.data["product_number_field"],
        "id_field": spec.confirmation.data["promise_product_id_field"],
        "date_field": spec.confirmation.data["promise_date_field"],
        "amount_field": spec.confirmation.data["promise_amount_field"],
    })
    return config


def _code(spec: PhoneAgentSpec, body: str, reset_variables: list[str]) -> str:
    return PRELUDE.replace("__CONFIG__", _py_literal(_full_config(spec, reset_variables))) + body


def offer_setup_code(spec: PhoneAgentSpec) -> str:
    """Per-product facts (earliest/latest date, min/max amount) and sentinels for prompts."""
    return _code(spec, SETUP_BODY, [])


def check_offer_code(spec: PhoneAgentSpec, reset_variables: list[str]) -> str:
    """Check the extracted offer against the spec rules; never raises."""
    return _code(spec, CHECK_BODY, reset_variables)


def promise_values_hook(spec: PhoneAgentSpec) -> str:
    """create_promise pre-hook: product id, date and amount come from checked offers."""
    return _code(spec, PROMISE_HOOK_BODY, [])
