import os
import re
import logging
import time
import openai
import requests
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
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

def get_guiding_question(condition_marker):
    bible_df = load_bible_data()
    if bible_df is None:
        return None
    for index, row in bible_df.iterrows():
        ver = str(row.get("Verification", "")).strip().upper()
        if ver == condition_marker.upper():
            question = row.get("FAQ", "").strip()
            logger.info(f"{get_rule('guiding_question_found')} {condition_marker}: {question}")
            return question
    logger.info(f"{get_rule('guiding_question_not_found')} {condition_marker}")
    return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    try:
        website_prices = get_ferry_prices()
        logger.info(f"{get_rule('website_prices_received')}: {website_prices}")
        
        # Выполняем поиск по типу транспортного средства без учета регистра
        key_match = None
        for key in website_prices:
            if key.lower() == vehicle_type:
                key_match = key
                break
        
        if key_match is None:
            msg = get_rule("price_not_found").format(vehicle_type=vehicle_type)
            logger.error(msg)
            return msg
        
        if direction == "Ro_Ge":
            website_price_str = website_prices[key_match].get("price_Ro_Ge", "")
        else:
            website_price_str = website_prices[key_match].get("price_Ge_Ro", "")
        
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
        remark = website_prices[key_match].get("remark", "")
        if remark:
            response_message += " " + remark
        conditions = website_prices[key_match].get("conditions", [])
        if conditions:
            response_message += "\n" + get_rule("guiding_questions_prompt")
            for marker in conditions:
                response_message += "\n" + marker
        return response_message
    except Exception as e:
        logger.error(f"{get_rule('price_error')}: {e}")
        return get_rule("price_error_message")

def get_openai_response(messages):
    start_time = time.time()
    attempt = 0
    while True:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150,
                timeout=40
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI error attempt {attempt+1}: {e}")
            attempt += 1
            if time.time() - start_time > 180:
                return get_rule("openai_timeout_message")
            time.sleep(2)
