import os
import re
import logging
import time
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import requests
from bible import load_bible_data, get_rule

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def remove_timestamp(text):
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        value = float(cleaned)
        logger.info(f"Parsed price from rule: {price_str} -> {value}")
        return value
    except Exception as e:
        logger.error(f"{get_rule('price_parse_error')}: {e}")
        return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    try:
        website_prices = get_ferry_prices()
        logger.info(f"{get_rule('website_prices_received')}: {website_prices}")
        
        if vehicle_type not in website_prices:
            msg = get_rule("price_not_found").format(vehicle_type=vehicle_type)
            logger.error(msg)
            return msg
        
        if direction == "Ro_Ge":
            website_price_str = website_prices[vehicle_type].get("price_Ro_Ge", "")
        else:
            website_price_str = website_prices[vehicle_type].get("price_Ge_Ro", "")
        
        website_price_str = remove_timestamp(website_price_str).strip()
        logger.info(f"Price for {vehicle_type}: '{website_price_str}'")
        
        if not re.search(r'\d', website_price_str) or website_price_str.upper() in ["PRICE_QUERY", "BASE_PRICE"]:
            logger.info(f"{get_rule('invalid_price_returned')} for {vehicle_type}")
            return website_price_str
        
        response_message = get_rule("price_response_template").format(
            vehicle_type=vehicle_type,
            direction=direction.replace('_', ' '),
            price=website_price_str
        )
        remark = website_prices[vehicle_type].get("remark", "")
        if remark:
            response_message += " " + remark
        conditions = website_prices[vehicle_type].get("conditions", [])
        if conditions:
            response_message += "\n" + get_rule("guiding_questions_prompt")
            for marker in conditions:
                response_message += "\n" + marker
        return response_message
    except Exception as e:
        logger.error(f"{get_rule('price_error')}: {e}")
        return get_rule("price_error_message")
