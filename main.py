"""
PR1NCE NUMBER BOT- Python Version
All features: Numbers, WhatsApp Check, OTP, Earnings, Withdraw, 2FA, TempMail, Admin, Referral
"""

import os
import io
import json
import hashlib
import re
import time
import random
import asyncio
import logging
import urllib.request
import urllib.parse
import urllib.error
import ipaddress
import subprocess
import threading
import sqlite3
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pyotp
from aiohttp import web as aio_web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, CopyTextButton, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ─── Zona Waktu: WIB (Waktu Indonesia Barat / UTC+7) ───
# Semua waktu yang ditampilkan atau disimpan di bot ini memakai WIB, dihitung
# dari UTC supaya benar walau timezone OS server hosting bukan UTC/WIB.
# now_wib() sengaja mengembalikan datetime NAIVE (tanpa tzinfo) supaya bisa
# langsung menggantikan semua pemanggilan datetime.now() yang lama tanpa
# merusak perbandingan/pengurangan datetime lain di file ini.
WIB = timezone(timedelta(hours=7))

def now_wib() -> datetime:
    """Waktu saat ini di WIB (UTC+7), sebagai datetime naive."""
    return (datetime.now(timezone.utc) + timedelta(hours=7)).replace(tzinfo=None)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─── Configuration ───
# Keep credentials out of the source archive. Set BOT_TOKEN (or
# TELEGRAM_BOT_TOKEN) in the deployment environment.
BOT_TOKEN = os.environ.get("8996328343:AAGH1K4gVNfPkgAsRVFPxCqaKMoO-cy1dpY") or os.environ.get("8996328343:AAGH1K4gVNfPkgAsRVFPxCqaKMoO-cy1dpY", "")

# ─── Owner IDs (hardcoded di SC) ───
# Pisahkan dengan koma jika lebih dari 1 owner, contoh: ["123456789", "987654321"]
OWNER_IDS = ["7770105316","8772990252"]

MAIN_CHANNEL     = "@lentfile"
MAIN_CHANNEL_URL = "https://t.me/lentfile"
MAIN_CHANNEL_ID  = -1003820329426
CHAT_GROUP       = "https://t.me/+KOnfBEknJMBmNDQ1"
CHAT_GROUP_ID    = -1004302965917
OTP_GROUP        = "https://t.me/+KOnfBEknJMBmNDQ1"
OTP_GROUP_ID     = -1004302965917

# ─── OTP Backlog Guard ───
# Setelah bot restart/start, Telegram bisa mengirim ulang pesan OTP lama yang
# tertunda (backlog) selama bot offline. Supaya nomor lama tidak salah
# ke-trigger sebagai OTP baru, pesan yang lebih tua dari ini akan diabaikan.
OTP_MAX_AGE_MINUTES = 1

# ─── Panel OTP replay policy ───
# Setiap polling panel hanya memproses 30 row terbaru. Row lama tidak dibuang
# berdasarkan umur; deduplikasi dilakukan terhadap otp_log yang persisten.
# Dengan begitu OTP baru yang muncul saat bot restart tetap diteruskan, tetapi
# OTP yang memang sudah pernah diteruskan tidak dikirim ulang.
PANEL_LATEST_ROWS_LIMIT = 30

# ─── Baileys API (WhatsApp) ───
BAILEYS_URL = os.environ.get("BAILEYS_URL", "http://localhost:3000")

# ─── Data Directory ───
DATA_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", os.path.dirname(os.path.abspath(__file__)))
logger.info(f"📁 Data Directory: {DATA_DIR}")

# ─── File Paths ───
NUMBERS_FILE        = os.path.join(DATA_DIR, "numbers.txt")
COUNTRIES_FILE      = os.path.join(DATA_DIR, "countries.json")
USERS_FILE          = os.path.join(DATA_DIR, "users.json")
SERVICES_FILE       = os.path.join(DATA_DIR, "services.json")
ACTIVE_NUMBERS_FILE = os.path.join(DATA_DIR, "active_numbers.json")
OTP_LOG_FILE        = os.path.join(DATA_DIR, "otp_log.json")
ADMINS_FILE         = os.path.join(DATA_DIR, "admins.json")
SETTINGS_FILE       = os.path.join(DATA_DIR, "settings.json")
TOTP_SECRETS_FILE   = os.path.join(DATA_DIR, "totp_secrets.json")
TEMP_MAILS_FILE     = os.path.join(DATA_DIR, "temp_mails.json")
EARNINGS_FILE       = os.path.join(DATA_DIR, "earnings.json")
WITHDRAW_FILE       = os.path.join(DATA_DIR, "withdrawals.json")
COUNTRY_PRICES_FILE = os.path.join(DATA_DIR, "country_prices.json")
WA_OWNER_FILE       = os.path.join(DATA_DIR, "wa_owner.json")
REFERRALS_FILE      = os.path.join(DATA_DIR, "referrals.json")
NUMBERS_CYCLE_FILE  = os.path.join(DATA_DIR, "numbers_cycle.json")
EMOJI_SETTINGS_FILE = os.path.join(DATA_DIR, "emoji_settings.json")

# ─── Default Settings ───
DEFAULT_SETTINGS = {
    "defaultNumberCount": 10,
    "cooldownSeconds": 5,
    "requireVerification": True,
    "minWithdraw": 50,
    "defaultOtpPrice": 0.25,
    "otpSearchWindowMinutes": 5,
    "otpSearchScope": "bot",
    "withdrawMethods": ["bKash", "Nagad"],
    "withdrawEnabled": True,
    "referralCommission": 10,
    "stockNotifyUsers": False,
    "featureToggles": {
        "getnumber": True,
        "getfile":   True,
        "cariotp":   True,
        "tempmail":  True,
        "twofa":     True,
        "balance":   True,
        "referral":  True,
        "support":   True,
        "cek_bio_wa": True,
        "fix_merah":  True,
    },
    "showCountOnCountryBtn": True,
    "cek_bio_wa_url": "https://t.me/yourbotname",
    "fix_merah_url":  "https://t.me/yourbotname",
    "hidden_number_mask":   "••••",
    "hidden_number_mask_id": None,
    "mask_prefix_digits":   4,
    "mask_suffix_digits":   2,
    "autoDeleteOtpEnabled": False,
    "autoDeleteOtpMinutes": 5,
}

# ─── Translations (EN / ID) ───
TRANSLATIONS = {
    "en": {
        # Main menu
        "btn_get_number":   "Get Number",
        "btn_get_file":     "Get File",
        "btn_search_otp":   "Search OTP",
        "btn_live_traffic": "Live Traffic",
        "btn_tools":        "Tools",
        "btn_profile":      "Profile",
        "btn_support":      "Support",
        "btn_minimize_menu":"Minimize Menu",
        "btn_language":     "🌐 Language",
        "menu_title":       "📌 <b>Main Menu</b> — choose from the buttons below 👇",
        "all_features_off": "❌ All features are currently disabled",
        "menu_minimized":   "🔽 <b>Menu minimized.</b>\n\nThe bottom menu is now hidden so it won't get in your way. Tap the button below (or send /menu) anytime to bring it back.",
        "menu_restore_btn": "📲 Show Menu",

        # Welcome / Start
        "welcome": (
            "👋 <b>Welcome to PR1NCE NUMBER BOT!</b>\n\n"
            "📱 Get virtual numbers for OTP verification\n"
            "💵 Earn money from each OTP received"
        ),
        "choose_option":   "✅ Choose an option:",
        "join_groups_msg": "First, join all required groups to use the bot:",
        "verify_success":  "✅ <b>VERIFICATION SUCCESSFUL!</b>\n\nYou can now use all features.",
        "welcome_back":    "🎉 Welcome! Choose an option:",
        "verify_fail":     "❌ <b>VERIFICATION FAILED</b>\n\nPlease join ALL groups and click VERIFY again.",
        "verify_prompt":   (
            "⚠️ <b>You must join all groups to use this bot!</b>\n\n"
            "Join all of the following, then press VERIFY:"
        ),
        "verify_alert":    "⛔ Please join all groups first!",

        # Numbers
        "no_numbers":          "📭 <b>No Numbers Available</b>\n\nPlease try again later.",
        "select_service":      "📋 <b>Choose a Service</b>\n\n_Stok tersedia ditampilkan dalam kurung ( )_",
        "select_country":      "Select Country",
        "numbers_assigned":    "✅ <b>{count} Number(s) Assigned!</b>",
        "otp_auto":            "📌 OTP will be delivered automatically.",
        "new_numbers":         "🔄 <b>{count} New Number(s)!</b>",
        "cooldown_wait":       "⏳ Please wait {sec} second(s).",
        "not_enough_numbers":  "❌ Not enough numbers available.",

        # Profile
        "profile_title":       "👤 <b>Your Profile</b>",
        "user_id":             "🆔 <b>User ID:</b>",
        "telegram_name":       "📛 <b>Telegram Name:</b>",
        "username":            "🔗 <b>Username:</b>",
        "total_balance":       "💰 <b>Total Balance:</b>",
        "otp_today":           "📨 <b>OTPs Today:</b>",
        "otp_all_time":        "📊 <b>Total OTPs (All Time):</b>",
        "profile_nav":         "Select a section below 👇",
        "language_current":    "🌐 <b>Language:</b> English",
        "switch_lang_btn":     "🇮🇩 Switch to Indonesian",

        # Balance
        "balance_title":       "💰 <b>Your Earnings</b>",
        "current_balance":     "💵 <b>Current Balance:</b>",
        "total_earned":        "📈 <b>Total Earned:</b>",
        "total_otps":          "📨 <b>Total OTPs:</b>",
        "total_withdrawn":     "💸 <b>Total Withdrawn:</b>",
        "pending_withdrawals": "⏳ <b>Pending Withdrawals:</b>",
        "referrals":           "👥 <b>Referrals:</b>",
        "referral_earnings":   "🎁 <b>Referral Earnings:</b>",
        "min_withdraw":        "📌 <b>Minimum Withdraw:</b>",

        # Withdraw
        "withdraw_disabled":   "⏸️ <b>Withdrawals are currently disabled.</b>",
        "insufficient_bal":    "❌ <b>Insufficient balance.</b>",
        "withdraw_title":      "💸 <b>Withdraw</b>",
        "choose_method":       "Choose method:",
        "withdraw_submitted":  "✅ <b>Withdrawal Request Submitted!</b>\n\n{method}\n📱 `{account}`\n💵 {amount:.2f} USD\n\n⏳ Pending admin approval.",
        "cancelled":           "❌ <b>Cancelled.</b>",

        # OTP Search
        "otp_search_title":    "🔍 <b>Search OTP</b>",
        "otp_invalid_number":  "❌ Invalid number. Send at least 3 digits or the full number.\n\nExample: <code>7484</code> or <code>+8801712345678</code>",
        "otp_not_found":       "❌ <b>OTP Not Found</b>\n\nNo OTP for `{digits}` in the last *{window} minutes*.\n\n_Check the number, or wait for the OTP and try again._",
        "otp_search_prompt":   (
            "🔍 <b>Search OTP</b>\n\n"
            "Send a number (last 4 digits or full number) to see OTPs in the last <b>{window} minutes</b>.\n\n"
            "Example: <code>7484</code> or <code>+8801712345678</code>\n\n"
            "You can also use <code>/otp 7484</code> at any time."
        ),
        "otp_results_title":   "🔍 <b>OTP Search Results</b> _(last {window} minutes)_\n",
        "otp_scope_bot":       "🤖 Bot Only (Private Chat)",
        "otp_scope_group":     "👥 Group Only",
        "otp_scope_all":       "🌐 All (Bot + Group)",
        "otp_scope_denied_bot":   "❌ <b>Search OTP</b> is only available in <b>private chat</b>, not in groups.",
        "otp_scope_denied_group": "❌ <b>Search OTP</b> is only available <b>inside a group</b>, not in private chat.",
        "otp_scope_denied":       "❌ <b>Search OTP</b> is not available here.",

        # Stock Notification (upload)
        "notify_title":       "🎉 <b>New Numbers Available!</b>",
        "notify_numbers_added": "➕ <b>Numbers Added</b>",
        "notify_service_label": "📞 <b>Service:</b>",
        "notify_country_label": "🌍 <b>Country:</b>",
        "notify_total_label":   "📊 <b>Total:</b>",
        "notify_numbers_unit":  "numbers",
        "notify_hurry":         "<i>Grab yours before they run out!</i>",
        "notify_get_number":    "☎️ Get Number",
        "notify_get_file":      "📁 Get File Number",

        # Tools
        "tools_title":        "🛠️ <b>Tools</b>\n\nChoose a tool:",
        "tools_unavailable":  "⏸️ <b>Tools</b> are currently unavailable (all tools disabled by admin).",

        # Temp Mail
        "tempmail_title":     "📧 <b>Temporary Email</b>",
        "email_your":         "📌 Your email:",
        "email_create":       "✅ Create a new disposable email address.",
        "email_created":      "✅ <b>New Email Created!</b>\n\n📧 `{address}`\n\n📌 Use this on any website.",
        "email_no_messages":  "📭 <b>No emails yet.</b>",
        "email_deleted":      "✅ <b>Email deleted.</b>",
        "email_not_found":    "❌ No email found.",
        "email_create_fail":  "❌ <b>Email creation failed.</b> Please try again.",

        # 2FA
        "twofa_title":        "🔐 <b>2-Step Verification Code Generator</b>\n\nSelect a service:",
        "twofa_code":         "🔑 <b>Code:</b> `{token}`\n\n⏰ *{remaining} seconds remaining*",
        "twofa_invalid":      "❌ Invalid secret key.",
        "twofa_secret_prompt": (
            "{icon} <b>{name} Secret Key</b>\n\n"
            "Send your Authenticator Secret Key.\n\n"
            "🔑 It looks like: <code>JBSWY3DPEHPK3PXP</code>\n\n"
            "Type /cancel to cancel"
        ),

        # Referral
        "referral_title":     "👥 <b>Referral Program</b>",
        "your_ref_link":      "🔗 Your referral link:",
        "commission_rate":    "💸 <b>Commission:</b> {rate}% per OTP",
        "ref_stats_label":    "📊 <b>Your Stats:</b>",
        "ref_count_label":    "  👥 Total Referrals:",
        "ref_earn_label":     "  💰 Total Commission Earned:",
        "ref_how":            (
            "📌 <b>How it works:</b>\n"
            "  1. Share your link above\n"
            "  2. When someone joins, they earn from OTPs\n"
            "  3. You receive <b>{rate}%</b> of their OTP income for life!\n"
        ),
        "no_referrals_yet":   "No referrals yet.",

        # Support
        "support_msg":        "💬 <b>Support</b>\n\nContact admin:\n📌 @pr1nceyuma",

        # Feature disabled
        "feature_disabled":   "⏸️ <b>{feature}</b> is currently disabled by the admin.\n\nPlease try again later.",

        # Verification
        "verify_btn":         "✅ VERIFY MEMBERSHIP",
        "main_channel_btn":   "1️⃣ 📢 Main Channel",
        "number_channel_btn": "2️⃣ 💬 Number Channel",
        "otp_group_btn":      "3️⃣ 📨 OTP Group",

        # Language selection
        "lang_select_title":  "🌐 <b>Language Settings</b>\n\nSelect your preferred language:",
        "lang_en":            "🇺🇸 English",
        "lang_id":            "🇮🇩 Indonesian (Bahasa Indonesia)",
        "lang_set_en":        "✅ Language set to <b>English</b>.",
        "lang_set_id":        "✅ Language set to <b>Indonesian</b> (Bahasa Indonesia).",

        # Get file
        "getfile_title":      (
            "📄 <b>Get File — Select Service</b>\n\n"
            "<i>(select service → select country → file .txt sent automatically)</i>"
        ),
        "getfile_select_country": "📄 {icon} <b>{name}</b> — Select Country",
        "file_ready":         (
            "📄 <b>File Ready!</b>\n\n"
            "{icon} <b>Service:</b> {name}\n"
            "{flag} <b>Country:</b> {country}\n"
            "🔢 <b>Total:</b> {count} numbers\n\n"
            "📌 OTPs will automatically appear in the OTP Group."
        ),
        "preparing_file":     "📎 Preparing .txt file, please wait...",

        # Time
        "time_ago_seconds":   "{n} seconds ago",
        "time_ago_minutes":   "{n} minutes ago",
        "time_ago_hours":     "{n} hours ago",
        "time_ago_days":      "{n} days ago",
        "just_now":           "just now",
    },

    "id": {
        # Main menu
        "btn_get_number":   "Dapatkan Nomor",
        "btn_get_file":     "Unduh File",
        "btn_search_otp":   "Cari OTP",
        "btn_live_traffic": "Trafik Langsung",
        "btn_tools":        "Alat",
        "btn_profile":      "Profil",
        "btn_support":      "Bantuan",
        "btn_minimize_menu":"Sembunyikan Menu",
        "btn_language":     "🌐 Bahasa",
        "menu_title":       "📌 <b>Menu Utama</b> — pilih tombol di bawah 👇",
        "all_features_off": "❌ Semua fitur saat ini dinonaktifkan",
        "menu_minimized":   "🔽 <b>Menu disembunyikan.</b>\n\nMenu bawah sekarang tersembunyi biar gak ganggu. Tap tombol di bawah (atau kirim /menu) kapan aja buat munculin lagi.",
        "menu_restore_btn": "📲 Tampilkan Menu",

        # Welcome / Start
        "welcome": (
            "👋 <b>Selamat datang di PR1NCE NUMBER BOT!</b>\n\n"
            "📱 Dapatkan nomor virtual untuk verifikasi OTP\n"
            "💵 Hasilkan uang dari setiap OTP yang diterima"
        ),
        "choose_option":   "✅ Pilih salah satu menu:",
        "join_groups_msg": "Bergabunglah dengan semua grup yang diwajibkan untuk menggunakan bot ini:",
        "verify_success":  "✅ <b>VERIFIKASI BERHASIL!</b>\n\nAnda sekarang bisa menggunakan semua fitur.",
        "welcome_back":    "🎉 Selamat datang! Pilih menu:",
        "verify_fail":     "❌ <b>VERIFIKASI GAGAL</b>\n\nSilakan bergabung ke SEMUA grup dan klik VERIFIKASI lagi.",
        "verify_prompt":   (
            "⚠️ <b>Anda harus bergabung ke semua grup untuk menggunakan bot ini!</b>\n\n"
            "Bergabunglah ke semua grup berikut, lalu tekan VERIFIKASI:"
        ),
        "verify_alert":    "⛔ Bergabunglah ke semua grup terlebih dahulu!",

        # Numbers
        "no_numbers":          "📭 <b>Tidak Ada Nomor Tersedia</b>\n\nSilakan coba lagi nanti.",
        "select_service":      "🎯 <b>Pilih Layanan</b>\n\n_(angka dalam kurung = jumlah tersedia)_",
        "select_country":      "Pilih Negara",
        "numbers_assigned":    "✅ <b>{count} Nomor Berhasil Ditetapkan!</b>",
        "otp_auto":            "📌 OTP akan dikirimkan secara otomatis.",
        "new_numbers":         "🔄 <b>{count} Nomor Baru!</b>",
        "cooldown_wait":       "⏳ Harap tunggu {sec} detik.",
        "not_enough_numbers":  "❌ Jumlah nomor tidak mencukupi.",

        # Profile
        "profile_title":       "👤 <b>Profil Anda</b>",
        "user_id":             "🆔 <b>User ID:</b>",
        "telegram_name":       "📛 <b>Nama Telegram:</b>",
        "username":            "🔗 <b>Username:</b>",
        "total_balance":       "💰 <b>Total Saldo:</b>",
        "otp_today":           "📨 <b>OTP Diterima Hari Ini:</b>",
        "otp_all_time":        "📊 <b>Total OTP Diterima (Sepanjang Masa):</b>",
        "profile_nav":         "Pilih menu di bawah 👇",
        "language_current":    "🌐 <b>Bahasa:</b> Indonesia",
        "switch_lang_btn":     "🇺🇸 Ganti ke Bahasa Inggris",

        # Balance
        "balance_title":       "💰 <b>Penghasilan Anda</b>",
        "current_balance":     "💵 <b>Saldo Saat Ini:</b>",
        "total_earned":        "📈 <b>Total Penghasilan:</b>",
        "total_otps":          "📨 <b>Total OTP:</b>",
        "total_withdrawn":     "💸 <b>Total Dicairkan:</b>",
        "pending_withdrawals": "⏳ <b>Penarikan Menunggu:</b>",
        "referrals":           "👥 <b>Referral:</b>",
        "referral_earnings":   "🎁 <b>Penghasilan Referral:</b>",
        "min_withdraw":        "📌 <b>Minimum Penarikan:</b>",

        # Withdraw
        "withdraw_disabled":   "⏸️ <b>Penarikan saat ini dinonaktifkan.</b>",
        "insufficient_bal":    "❌ <b>Saldo tidak mencukupi.</b>",
        "withdraw_title":      "💸 <b>Penarikan Dana</b>",
        "choose_method":       "Pilih metode:",
        "withdraw_submitted":  "✅ <b>Permintaan Penarikan Berhasil Dikirim!</b>\n\n{method}\n📱 `{account}`\n💵 {amount:.2f} USD\n\n⏳ Menunggu persetujuan admin.",
        "cancelled":           "❌ <b>Dibatalkan.</b>",

        # OTP Search
        "otp_search_title":    "🔍 <b>Cari OTP</b>",
        "otp_invalid_number":  "❌ Nomor tidak valid. Kirim minimal 3 digit terakhir atau nomor lengkap.\n\nContoh: <code>7484</code> atau <code>+8801712345678</code>",
        "otp_not_found":       "❌ <b>OTP Tidak Ditemukan</b>\n\nTidak ada OTP untuk `{digits}` dalam *{window} menit* terakhir.\n\n_Periksa kembali nomornya, atau tunggu OTP masuk lalu coba lagi._",
        "otp_search_prompt":   (
            "🔍 <b>Cari OTP</b>\n\n"
            "Kirim nomor (4 digit terakhir atau nomor lengkap) untuk melihat OTP dalam <b>{window} menit</b> terakhir.\n\n"
            "Contoh: <code>7484</code> atau <code>+8801712345678</code>\n\n"
            "Anda juga bisa langsung ketik <code>/otp 7484</code> kapan saja."
        ),
        "otp_results_title":   "🔍 <b>Hasil Pencarian OTP</b> _(dalam {window} menit terakhir)_\n",
        "otp_scope_bot":       "🤖 Bot Saja (Chat Pribadi)",
        "otp_scope_group":     "👥 Grup Saja",
        "otp_scope_all":       "🌐 Semua (Bot + Grup)",
        "otp_scope_denied_bot":   "❌ <b>Cari OTP</b> hanya bisa digunakan di <b>chat pribadi bot</b>, bukan di grup.",
        "otp_scope_denied_group": "❌ <b>Cari OTP</b> hanya bisa digunakan <b>di dalam grup</b>, bukan di chat pribadi bot.",
        "otp_scope_denied":       "❌ <b>Cari OTP</b> tidak tersedia di sini.",

        # Stock Notification (upload)
        "notify_title":       "🎉 <b>Nomor Baru Tersedia!</b>",
        "notify_numbers_added": "➕ <b>Nomor Ditambahkan</b>",
        "notify_service_label": "📞 <b>Layanan:</b>",
        "notify_country_label": "🌍 <b>Negara:</b>",
        "notify_total_label":   "📊 <b>Total:</b>",
        "notify_numbers_unit":  "nomor",
        "notify_hurry":         "<i>Segera ambil sebelum kehabisan!</i>",
        "notify_get_number":    "☎️ Ambil Nomor",
        "notify_get_file":      "📁 Ambil File Nomor",

        # Tools
        "tools_title":        "🛠️ <b>Alat</b>\n\nPilih alat yang ingin digunakan:",
        "tools_unavailable":  "⏸️ <b>Alat</b> saat ini tidak tersedia (semua alat dinonaktifkan admin).",

        # Temp Mail
        "tempmail_title":     "📧 <b>Email Sementara</b>",
        "email_your":         "📌 Email Anda:",
        "email_create":       "✅ Buat alamat email sekali pakai baru.",
        "email_created":      "✅ <b>Email Baru Berhasil Dibuat!</b>\n\n📧 `{address}`\n\n📌 Gunakan ini di situs web mana saja.",
        "email_no_messages":  "📭 <b>Belum ada email.</b>",
        "email_deleted":      "✅ <b>Email dihapus.</b>",
        "email_not_found":    "❌ Email tidak ditemukan.",
        "email_create_fail":  "❌ <b>Pembuatan email gagal.</b> Silakan coba lagi.",

        # 2FA
        "twofa_title":        "🔐 <b>Generator Kode Verifikasi 2 Langkah</b>\n\nPilih layanan:",
        "twofa_code":         "🔑 <b>Kode:</b> `{token}`\n\n⏰ *{remaining} detik tersisa*",
        "twofa_invalid":      "❌ Kunci rahasia tidak valid.",
        "twofa_secret_prompt": (
            "{icon} <b>Kunci Rahasia {name}</b>\n\n"
            "Kirim Kunci Rahasia Authenticator Anda.\n\n"
            "🔑 Bentuknya seperti: <code>JBSWY3DPEHPK3PXP</code>\n\n"
            "Ketik /cancel untuk membatalkan"
        ),

        # Referral
        "referral_title":     "👥 <b>Program Referral</b>",
        "your_ref_link":      "🔗 Link referral Anda:",
        "commission_rate":    "💸 <b>Komisi:</b> {rate}% per OTP",
        "ref_stats_label":    "📊 <b>Statistik Anda:</b>",
        "ref_count_label":    "  👥 Total Referral:",
        "ref_earn_label":     "  💰 Total Komisi Diperoleh:",
        "ref_how":            (
            "📌 <b>Cara kerjanya:</b>\n"
            "  1. Bagikan link Anda di atas\n"
            "  2. Saat seseorang bergabung, mereka mendapat penghasilan dari OTP\n"
            "  3. Anda menerima <b>{rate}%</b> dari setiap penghasilan OTP mereka seumur hidup!\n"
        ),
        "no_referrals_yet":   "Belum ada referral.",

        # Support
        "support_msg":        "💬 <b>Bantuan</b>\n\nHubungi admin:\n📌 @pr1nceyuma",

        # Feature disabled
        "feature_disabled":   "⏸️ <b>{feature}</b> saat ini dinonaktifkan oleh admin.\n\nSilakan coba lagi nanti.",

        # Verification
        "verify_btn":         "✅ VERIFIKASI KEANGGOTAAN",
        "main_channel_btn":   "1️⃣ 📢 Kanal Utama",
        "number_channel_btn": "2️⃣ 💬 Kanal Nomor",
        "otp_group_btn":      "3️⃣ 📨 Grup OTP",

        # Language selection
        "lang_select_title":  "🌐 <b>Pengaturan Bahasa</b>\n\nPilih bahasa yang Anda inginkan:",
        "lang_en":            "🇺🇸 Bahasa Inggris (English)",
        "lang_id":            "🇮🇩 Bahasa Indonesia",
        "lang_set_en":        "✅ Bahasa diatur ke <b>Bahasa Inggris</b> (English).",
        "lang_set_id":        "✅ Bahasa diatur ke <b>Bahasa Indonesia</b>.",

        # Get file
        "getfile_title":      (
            "📄 <b>Unduh File — Pilih Layanan</b>\n\n"
            "<i>(pilih layanan → pilih negara → file .txt dikirim otomatis)</i>"
        ),
        "getfile_select_country": "📄 {icon} <b>{name}</b> — Pilih Negara",
        "file_ready":         (
            "📄 <b>File Siap!</b>\n\n"
            "{icon} <b>Layanan:</b> {name}\n"
            "{flag} <b>Negara:</b> {country}\n"
            "🔢 <b>Total:</b> {count} nomor\n\n"
            "📌 OTP akan otomatis muncul di Grup OTP."
        ),
        "preparing_file":     "📎 Menyiapkan file .txt, harap tunggu...",

        # Time
        "time_ago_seconds":   "{n} detik yang lalu",
        "time_ago_minutes":   "{n} menit yang lalu",
        "time_ago_hours":     "{n} jam yang lalu",
        "time_ago_days":      "{n} hari yang lalu",
        "just_now":           "baru saja",
    },
}

def get_user_lang(uid: str) -> str:
    """Return user's language preference: 'en' or 'id' (default 'en')."""
    return users.get(str(uid), {}).get("language", "en")

def t(uid: str, key: str, **kwargs) -> str:
    """Translate a key for a user. Falls back to English if key not found."""
    lang = get_user_lang(str(uid))
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    text = lang_dict.get(key) or TRANSLATIONS["en"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text

import re as _re
_MD_PRE    = _re.compile(r'<pre>([\s\S]*?)</pre>')
_MD_CODE   = _re.compile(r'<code>([^</code>\n]+)`')
_MD_BOLD   = _re.compile(r'\<b>([^</b>\n]+)\*')
_MD_ITALIC = _re.compile(r'(?<![\\w])<i>([^</i>\n]+)_(?![\\w])')

def md2html(text: str) -> str:
    """Konversi Telegram Markdown sederhana → HTML (untuk parse_mode='HTML').
    Menangani: <b>bold</b> → <b>, <i>italic</i> → <i>, <code>code</code> → <code>, <pre>pre</pre> → <pre>.
    Catatan: TIDAK melakukan html.escape() — pemanggil harus escape data dinamis."""
    text = _MD_PRE.sub(lambda m: f'<pre>{m.group(1)}</pre>', text)
    text = _MD_CODE.sub(lambda m: f'<code>{m.group(1)}</code>', text)
    text = _MD_BOLD.sub(lambda m: f'<b>{m.group(1)}</b>', text)
    text = _MD_ITALIC.sub(lambda m: f'<i>{m.group(1)}</i>', text)
    return text

def t_html(uid: str, key: str, **kwargs) -> str:
    """Seperti t() tapi mengembalikan string HTML (Markdown dikonversi ke HTML).
    kwargs di-escape dengan html.escape() sebelum dimasukkan ke template."""
    lang = get_user_lang(str(uid))
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    raw = lang_dict.get(key) or TRANSLATIONS["en"].get(key, key)
    html_tmpl = md2html(raw)
    if kwargs:
        try:
            escaped = {k: html.escape(str(v)) for k, v in kwargs.items()}
            html_tmpl = html_tmpl.format(**escaped)
        except Exception:
            pass
    return html_tmpl

# ─── Load/Save Helpers ───
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
    return default

def save_json(path, data):
    # BUG FIX: sebelumnya nulis langsung ke `path` dengan mode "w". Kalau bot
    # crash/di-kill/kehabisan disk tepat di tengah proses tulis, file JSON
    # jadi kepotong (corrupt) — saat load_json() baca file itu lagi, parsing
    # gagal dan SEMUA data di file itu (saldo, nomor aktif, dll) hilang balik
    # ke default. Supaya aman, tulis dulu ke file sementara lalu ganti nama
    # (os.replace) yang atomic di level OS — file asli tidak pernah dalam
    # keadaan "setengah tertulis".
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

# ─── Load Data ───
settings       = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
if "referralCommission" not in settings:
    settings["referralCommission"] = 10
if "otpSearchWindowMinutes" not in settings:
    settings["otpSearchWindowMinutes"] = 5
if "otpSearchScope" not in settings:
    settings["otpSearchScope"] = "bot"
if "featureToggles" not in settings:
    settings["featureToggles"] = dict(DEFAULT_SETTINGS["featureToggles"])
else:
    for _fk, _fv in DEFAULT_SETTINGS["featureToggles"].items():
        settings["featureToggles"].setdefault(_fk, _fv)
if "cek_bio_wa_url" not in settings:
    settings["cek_bio_wa_url"] = DEFAULT_SETTINGS["cek_bio_wa_url"]
if "fix_merah_url" not in settings:
    settings["fix_merah_url"] = DEFAULT_SETTINGS["fix_merah_url"]
if "hidden_number_mask" not in settings:
    settings["hidden_number_mask"] = DEFAULT_SETTINGS["hidden_number_mask"]
if "hidden_number_mask_id" not in settings:
    settings["hidden_number_mask_id"] = DEFAULT_SETTINGS["hidden_number_mask_id"]
if "mask_prefix_digits" not in settings:
    settings["mask_prefix_digits"] = DEFAULT_SETTINGS["mask_prefix_digits"]
if "mask_suffix_digits" not in settings:
    settings["mask_suffix_digits"] = DEFAULT_SETTINGS["mask_suffix_digits"]
if "autoDeleteOtpEnabled" not in settings:
    settings["autoDeleteOtpEnabled"] = DEFAULT_SETTINGS["autoDeleteOtpEnabled"]
if "autoDeleteOtpMinutes" not in settings:
    settings["autoDeleteOtpMinutes"] = DEFAULT_SETTINGS["autoDeleteOtpMinutes"]

users          = load_json(USERS_FILE, {})
active_numbers = load_json(ACTIVE_NUMBERS_FILE, {})
otp_log        = load_json(OTP_LOG_FILE, [])
admins         = load_json(ADMINS_FILE, [])
# Pastikan semua OWNER_IDS selalu masuk ke daftar admins
for _oid in OWNER_IDS:
    if _oid not in admins:
        admins.append(_oid)
totp_secrets   = load_json(TOTP_SECRETS_FILE, {})
temp_mails     = load_json(TEMP_MAILS_FILE, {})
earnings       = load_json(EARNINGS_FILE, {})
withdrawals    = load_json(WITHDRAW_FILE, [])
country_prices = load_json(COUNTRY_PRICES_FILE, {})
referrals      = load_json(REFERRALS_FILE, {})
wa_sessions    = {}

# ─── Global WhatsApp System ───
# admin একটা WA connect করলে সব user এর number check হবে
GLOBAL_WA_FILE    = os.path.join(DATA_DIR, "global_wa.json")
global_wa_data    = load_json(GLOBAL_WA_FILE, {
    "enabled":   False,   # Global WA check on/off
    "connected": False,   # Admin WA connected কিনা
    "phone":     "",      # Admin WA phone
    "uid":       "",      # Admin WA session uid
})

def save_global_wa():
    save_json(GLOBAL_WA_FILE, global_wa_data)
_tg_app        = None

countries = load_json(COUNTRIES_FILE, {
    "880": {"name": "Bangladesh", "flag": "🇧🇩", "iso": "BD"},
    "91": {"name": "India", "flag": "🇮🇳", "iso": "IN"},
    "92": {"name": "Pakistan", "flag": "🇵🇰", "iso": "PK"},
    "977": {"name": "Nepal", "flag": "🇳🇵", "iso": "NP"},
    "94": {"name": "Sri Lanka", "flag": "🇱🇰", "iso": "LK"},
    "95": {"name": "Myanmar", "flag": "🇲🇲", "iso": "MM"},
    "975": {"name": "Bhutan", "flag": "🇧🇹", "iso": "BT"},
    "960": {"name": "Maldives", "flag": "🇲🇻", "iso": "MV"},
    "66": {"name": "Thailand", "flag": "🇹🇭", "iso": "TH"},
    "84": {"name": "Vietnam", "flag": "🇻🇳", "iso": "VN"},
    "62": {"name": "Indonesia", "flag": "🇮🇩", "iso": "ID"},
    "60": {"name": "Malaysia", "flag": "🇲🇾", "iso": "MY"},
    "63": {"name": "Philippines", "flag": "🇵🇭", "iso": "PH"},
    "65": {"name": "Singapore", "flag": "🇸🇬", "iso": "SG"},
    "855": {"name": "Cambodia", "flag": "🇰🇭", "iso": "KH"},
    "856": {"name": "Laos", "flag": "🇱🇦", "iso": "LA"},
    "673": {"name": "Brunei", "flag": "🇧🇳", "iso": "BN"},
    "670": {"name": "Timor-Leste", "flag": "🇹🇱", "iso": "TL"},
    "86": {"name": "China", "flag": "🇨🇳", "iso": "CN"},
    "81": {"name": "Japan", "flag": "🇯🇵", "iso": "JP"},
    "82": {"name": "South Korea", "flag": "🇰🇷", "iso": "KR"},
    "886": {"name": "Taiwan", "flag": "🇹🇼", "iso": "TW"},
    "852": {"name": "Hong Kong", "flag": "🇭🇰", "iso": "HK"},
    "853": {"name": "Macau", "flag": "🇲🇴", "iso": "MO"},
    "976": {"name": "Mongolia", "flag": "🇲🇳", "iso": "MN"},
    "850": {"name": "North Korea", "flag": "🇰🇵", "iso": "KP"},
    "7": {"name": "Russia", "flag": "🇷🇺", "iso": "RU"},
    "996": {"name": "Kyrgyzstan", "flag": "🇰🇬", "iso": "KG"},
    "992": {"name": "Tajikistan", "flag": "🇹🇯", "iso": "TJ"},
    "993": {"name": "Turkmenistan", "flag": "🇹🇲", "iso": "TM"},
    "998": {"name": "Uzbekistan", "flag": "🇺🇿", "iso": "UZ"},
    "7778": {"name": "Kazakhstan", "flag": "🇰🇿", "iso": "KZ"},
    "93": {"name": "Afghanistan", "flag": "🇦🇫", "iso": "AF"},
    "98": {"name": "Iran", "flag": "🇮🇷", "iso": "IR"},
    "964": {"name": "Iraq", "flag": "🇮🇶", "iso": "IQ"},
    "963": {"name": "Syria", "flag": "🇸🇾", "iso": "SY"},
    "961": {"name": "Lebanon", "flag": "🇱🇧", "iso": "LB"},
    "962": {"name": "Jordan", "flag": "??🇴", "iso": "JO"},
    "972": {"name": "Israel", "flag": "🇮🇱", "iso": "IL"},
    "970": {"name": "Palestine", "flag": "🇵🇸", "iso": "PS"},
    "966": {"name": "Saudi Arabia", "flag": "🇸🇦", "iso": "SA"},
    "971": {"name": "UAE", "flag": "🇦🇪", "iso": "AE"},
    "974": {"name": "Qatar", "flag": "🇶🇦", "iso": "QA"},
    "973": {"name": "Bahrain", "flag": "🇧🇭", "iso": "BH"},
    "965": {"name": "Kuwait", "flag": "🇰🇼", "iso": "KW"},
    "968": {"name": "Oman", "flag": "🇴🇲", "iso": "OM"},
    "967": {"name": "Yemen", "flag": "🇾🇪", "iso": "YE"},
    "90": {"name": "Turkey", "flag": "🇹🇷", "iso": "TR"},
    "994": {"name": "Azerbaijan", "flag": "🇦🇿", "iso": "AZ"},
    "374": {"name": "Armenia", "flag": "🇦🇲", "iso": "AM"},
    "995": {"name": "Georgia", "flag": "🇬🇪", "iso": "GE"},
    "44": {"name": "UK", "flag": "🇬🇧", "iso": "GB"},
    "49": {"name": "Germany", "flag": "🇩🇪", "iso": "DE"},
    "33": {"name": "France", "flag": "🇫🇷", "iso": "FR"},
    "39": {"name": "Italy", "flag": "🇮🇹", "iso": "IT"},
    "34": {"name": "Spain", "flag": "🇪🇸", "iso": "ES"},
    "31": {"name": "Netherlands", "flag": "🇳🇱", "iso": "NL"},
    "32": {"name": "Belgium", "flag": "🇧🇪", "iso": "BE"},
    "41": {"name": "Switzerland", "flag": "🇨🇭", "iso": "CH"},
    "43": {"name": "Austria", "flag": "🇦🇹", "iso": "AT"},
    "351": {"name": "Portugal", "flag": "🇵🇹", "iso": "PT"},
    "353": {"name": "Ireland", "flag": "🇮🇪", "iso": "IE"},
    "352": {"name": "Luxembourg", "flag": "🇱🇺", "iso": "LU"},
    "356": {"name": "Malta", "flag": "🇲🇹", "iso": "MT"},
    "357": {"name": "Cyprus", "flag": "🇨🇾", "iso": "CY"},
    "45": {"name": "Denmark", "flag": "🇩🇰", "iso": "DK"},
    "46": {"name": "Sweden", "flag": "🇸🇪", "iso": "SE"},
    "47": {"name": "Norway", "flag": "🇳🇴", "iso": "NO"},
    "358": {"name": "Finland", "flag": "🇫🇮", "iso": "FI"},
    "354": {"name": "Iceland", "flag": "🇮🇸", "iso": "IS"},
    "370": {"name": "Lithuania", "flag": "🇱🇹", "iso": "LT"},
    "371": {"name": "Latvia", "flag": "🇱🇻", "iso": "LV"},
    "372": {"name": "Estonia", "flag": "🇪🇪", "iso": "EE"},
    "30": {"name": "Greece", "flag": "🇬🇷", "iso": "GR"},
    "48": {"name": "Poland", "flag": "🇵🇱", "iso": "PL"},
    "420": {"name": "Czech Rep.", "flag": "🇨🇿", "iso": "CZ"},
    "421": {"name": "Slovakia", "flag": "🇸🇰", "iso": "SK"},
    "36": {"name": "Hungary", "flag": "🇭🇺", "iso": "HU"},
    "40": {"name": "Romania", "flag": "🇷🇴", "iso": "RO"},
    "359": {"name": "Bulgaria", "flag": "🇧🇬", "iso": "BG"},
    "385": {"name": "Croatia", "flag": "🇭🇷", "iso": "HR"},
    "381": {"name": "Serbia", "flag": "🇷🇸", "iso": "RS"},
    "387": {"name": "Bosnia", "flag": "🇧🇦", "iso": "BA"},
    "386": {"name": "Slovenia", "flag": "🇸🇮", "iso": "SI"},
    "382": {"name": "Montenegro", "flag": "🇲🇪", "iso": "ME"},
    "389": {"name": "N. Macedonia", "flag": "🇲🇰", "iso": "MK"},
    "355": {"name": "Albania", "flag": "🇦🇱", "iso": "AL"},
    "373": {"name": "Moldova", "flag": "🇲🇩", "iso": "MD"},
    "380": {"name": "Ukraine", "flag": "🇺🇦", "iso": "UA"},
    "375": {"name": "Belarus", "flag": "🇧🇾", "iso": "BY"},
    "383": {"name": "Kosovo", "flag": "🇽🇰", "iso": "XK"},
    "1": {"name": "USA/Canada", "flag": "🇺🇸", "iso": "US"},
    "52": {"name": "Mexico", "flag": "🇲🇽", "iso": "MX"},
    "506": {"name": "Costa Rica", "flag": "🇨🇷", "iso": "CR"},
    "502": {"name": "Guatemala", "flag": "🇬🇹", "iso": "GT"},
    "504": {"name": "Honduras", "flag": "🇭🇳", "iso": "HN"},
    "503": {"name": "El Salvador", "flag": "🇸🇻", "iso": "SV"},
    "505": {"name": "Nicaragua", "flag": "🇳🇮", "iso": "NI"},
    "507": {"name": "Panama", "flag": "🇵🇦", "iso": "PA"},
    "53": {"name": "Cuba", "flag": "🇨🇺", "iso": "CU"},
    "509": {"name": "Haiti", "flag": "🇭🇹", "iso": "HT"},
    "501": {"name": "Belize", "flag": "🇧🇿", "iso": "BZ"},
    "55": {"name": "Brazil", "flag": "🇧🇷", "iso": "BR"},
    "54": {"name": "Argentina", "flag": "🇦🇷", "iso": "AR"},
    "56": {"name": "Chile", "flag": "🇨🇱", "iso": "CL"},
    "57": {"name": "Colombia", "flag": "🇨🇴", "iso": "CO"},
    "51": {"name": "Peru", "flag": "🇵🇪", "iso": "PE"},
    "58": {"name": "Venezuela", "flag": "🇻🇪", "iso": "VE"},
    "593": {"name": "Ecuador", "flag": "🇪🇨", "iso": "EC"},
    "591": {"name": "Bolivia", "flag": "🇧🇴", "iso": "BO"},
    "595": {"name": "Paraguay", "flag": "🇵🇾", "iso": "PY"},
    "598": {"name": "Uruguay", "flag": "🇺🇾", "iso": "UY"},
    "592": {"name": "Guyana", "flag": "🇬🇾", "iso": "GY"},
    "597": {"name": "Suriname", "flag": "🇸🇷", "iso": "SR"},
    "20": {"name": "Egypt", "flag": "🇪🇬", "iso": "EG"},
    "213": {"name": "Algeria", "flag": "🇩🇿", "iso": "DZ"},
    "212": {"name": "Morocco", "flag": "🇲🇦", "iso": "MA"},
    "216": {"name": "Tunisia", "flag": "🇹🇳", "iso": "TN"},
    "218": {"name": "Libya", "flag": "🇱🇾", "iso": "LY"},
    "249": {"name": "Sudan", "flag": "🇸🇩", "iso": "SD"},
    "234": {"name": "Nigeria", "flag": "🇳🇬", "iso": "NG"},
    "233": {"name": "Ghana", "flag": "🇬🇭", "iso": "GH"},
    "221": {"name": "Senegal", "flag": "🇸🇳", "iso": "SN"},
    "225": {"name": "Côte d'Ivoire", "flag": "🇨🇮", "iso": "CI"},
    "222": {"name": "Mauritania", "flag": "🇲🇷", "iso": "MR"},
    "223": {"name": "Mali", "flag": "🇲🇱", "iso": "ML"},
    "226": {"name": "Burkina Faso", "flag": "🇧🇫", "iso": "BF"},
    "227": {"name": "Niger", "flag": "🇳🇪", "iso": "NE"},
    "228": {"name": "Togo", "flag": "🇹🇬", "iso": "TG"},
    "229": {"name": "Benin", "flag": "🇧🇯", "iso": "BJ"},
    "232": {"name": "Sierra Leone", "flag": "🇸🇱", "iso": "SL"},
    "231": {"name": "Liberia", "flag": "🇱🇷", "iso": "LR"},
    "224": {"name": "Guinea", "flag": "🇬🇳", "iso": "GN"},
    "245": {"name": "Guinea-Bissau", "flag": "🇬🇼", "iso": "GW"},
    "238": {"name": "Cape Verde", "flag": "🇨🇻", "iso": "CV"},
    "237": {"name": "Cameroon", "flag": "🇨🇲", "iso": "CM"},
    "243": {"name": "DR Congo", "flag": "🇨🇩", "iso": "CD"},
    "242": {"name": "Congo", "flag": "🇨🇬", "iso": "CG"},
    "240": {"name": "Eq. Guinea", "flag": "🇬🇶", "iso": "GQ"},
    "241": {"name": "Gabon", "flag": "🇬🇦", "iso": "GA"},
    "236": {"name": "CAR", "flag": "🇨🇫", "iso": "CF"},
    "235": {"name": "Chad", "flag": "🇹🇩", "iso": "TD"},
    "254": {"name": "Kenya", "flag": "🇰🇪", "iso": "KE"},
    "255": {"name": "Tanzania", "flag": "🇹🇿", "iso": "TZ"},
    "256": {"name": "Uganda", "flag": "🇺🇬", "iso": "UG"},
    "251": {"name": "Ethiopia", "flag": "🇪🇹", "iso": "ET"},
    "252": {"name": "Somalia", "flag": "🇸🇴", "iso": "SO"},
    "253": {"name": "Djibouti", "flag": "🇩🇯", "iso": "DJ"},
    "257": {"name": "Burundi", "flag": "🇧🇮", "iso": "BI"},
    "250": {"name": "Rwanda", "flag": "🇷🇼", "iso": "RW"},
    "291": {"name": "Eritrea", "flag": "🇪🇷", "iso": "ER"},
    "27": {"name": "South Africa", "flag": "🇿🇦", "iso": "ZA"},
    "258": {"name": "Mozambique", "flag": "🇲🇿", "iso": "MZ"},
    "260": {"name": "Zambia", "flag": "🇿🇲", "iso": "ZM"},
    "263": {"name": "Zimbabwe", "flag": "🇿🇼", "iso": "ZW"},
    "267": {"name": "Botswana", "flag": "🇧🇼", "iso": "BW"},
    "264": {"name": "Namibia", "flag": "🇳🇦", "iso": "NA"},
    "266": {"name": "Lesotho", "flag": "🇱🇸", "iso": "LS"},
    "268": {"name": "Eswatini", "flag": "🇸🇿", "iso": "SZ"},
    "244": {"name": "Angola", "flag": "🇦🇴", "iso": "AO"},
    "261": {"name": "Madagascar", "flag": "🇲🇬", "iso": "MG"},
    "230": {"name": "Mauritius", "flag": "🇲🇺", "iso": "MU"},
    "248": {"name": "Seychelles", "flag": "🇸🇨", "iso": "SC"},
    "61": {"name": "Australia", "flag": "🇦🇺", "iso": "AU"},
    "64": {"name": "New Zealand", "flag": "🇳🇿", "iso": "NZ"},
    "679": {"name": "Fiji", "flag": "🇫🇯", "iso": "FJ"},
    "675": {"name": "Papua NG", "flag": "🇵🇬", "iso": "PG"},
    "677": {"name": "Solomon Is.", "flag": "🇸🇧", "iso": "SB"},
    "678": {"name": "Vanuatu", "flag": "🇻🇺", "iso": "VU"},
    "676": {"name": "Tonga", "flag": "🇹🇴", "iso": "TO"},
    "685": {"name": "Samoa", "flag": "🇼🇸", "iso": "WS"},
    "686": {"name": "Kiribati", "flag": "🇰🇮", "iso": "KI"},
    "688": {"name": "Tuvalu", "flag": "🇹🇻", "iso": "TV"},
    "692": {"name": "Marshall Is.", "flag": "🇲🇭", "iso": "MH"},
    "691": {"name": "Micronesia", "flag": "🇫🇲", "iso": "FM"},
    "680": {"name": "Palau", "flag": "🇵🇼", "iso": "PW"},
    "674": {"name": "Nauru", "flag": "🇳🇷", "iso": "NR"},
    "682": {"name": "Cook Islands", "flag": "🇨🇰", "iso": "CK"},
    "683": {"name": "Niue", "flag": "🇳🇺", "iso": "NU"},
    "690": {"name": "Tokelau", "flag": "🇹🇰", "iso": "TK"},
    "681": {"name": "Wallis & Futuna", "flag": "🇼🇫", "iso": "WF"},
    "687": {"name": "New Caledonia", "flag": "🇳🇨", "iso": "NC"},
    "689": {"name": "French Polynesia", "flag": "🇵🇫", "iso": "PF"},
    "1684": {"name": "American Samoa", "flag": "🇦🇸", "iso": "AS"},
    "1671": {"name": "Guam", "flag": "🇬🇺", "iso": "GU"},
    "1670": {"name": "N. Mariana Is.", "flag": "🇲🇵", "iso": "MP"},
    "376": {"name": "Andorra", "flag": "🇦🇩", "iso": "AD"},
    "377": {"name": "Monaco", "flag": "🇲🇨", "iso": "MC"},
    "378": {"name": "San Marino", "flag": "🇸🇲", "iso": "SM"},
    "379": {"name": "Vatican City", "flag": "🇻🇦", "iso": "VA"},
    "423": {"name": "Liechtenstein", "flag": "🇱🇮", "iso": "LI"},
    "350": {"name": "Gibraltar", "flag": "🇬🇮", "iso": "GI"},
    "298": {"name": "Faroe Islands", "flag": "🇫🇴", "iso": "FO"},
    "299": {"name": "Greenland", "flag": "🇬🇱", "iso": "GL"},
    "211": {"name": "South Sudan", "flag": "🇸🇸", "iso": "SS"},
    "269": {"name": "Comoros", "flag": "🇰🇲", "iso": "KM"},
    "239": {"name": "Sao Tome & Principe", "flag": "🇸🇹", "iso": "ST"},
})

services = load_json(SERVICES_FILE, {
    "whatsapp":    {"name": "WhatsApp",    "icon": "📱"},
    "telegram":    {"name": "Telegram",    "icon": "✈️"},
    "facebook":    {"name": "Facebook",    "icon": "📘"},
    "instagram":   {"name": "Instagram",   "icon": "📸"},
    "google":      {"name": "Google",      "icon": "🔍"},
    "verification":{"name": "Verification","icon": "✅"},
    "other":       {"name": "Other",       "icon": "🔧"},
})

# ─── Service baru dari daftar SERVICE_ASSETS (di-"tanam" langsung di SC) ───
# Kalau service ini belum ada (baik di deployment baru maupun yang sudah
# jalan dan sudah punya services.json lama), otomatis ditambahkan lalu
# disimpan ke services.json — admin tidak perlu menambah manual satu-satu.
_NEW_SERVICE_DEFAULTS = {
    "apple": {"name": "Apple", "icon": "🍎"},
    "bitget": {"name": "Bitget", "icon": "💹"},
    "discord": {"name": "Discord", "icon": "🎮"},
    "imo": {"name": "IMO", "icon": "📞"},
    "lazada": {"name": "Lazada", "icon": "🛍️"},
    "microsoft": {"name": "Microsoft", "icon": "🪟"},
    "netflix": {"name": "Netflix", "icon": "🎬"},
    "shopee": {"name": "Shopee", "icon": "🛒"},
    "snapchat": {"name": "Snapchat", "icon": "👻"},
    "tiktok": {"name": "TikTok", "icon": "🎵"},
    "tinder": {"name": "Tinder", "icon": "🔥"},
    "twitter": {"name": "Twitter/X", "icon": "🐦"},
    "wechat": {"name": "WeChat", "icon": "💬"},
    "xiaomi": {"name": "Xiaomi", "icon": "📱"},
}
_services_changed = False
for _svc_key, _svc_info in _NEW_SERVICE_DEFAULTS.items():
    if _svc_key not in services:
        services[_svc_key] = _svc_info
        _services_changed = True
if _services_changed:
    save_json(SERVICES_FILE, services)
    logger.info(f"✅ {len(_NEW_SERVICE_DEFAULTS)} service baru dicek/ditambahkan ke services.json")

# ─── Custom Emoji Settings (disimpan permanen di database SQLite) ───
# Tabel `custom_emoji` di custom_emoji.db, bukan lagi file JSON, supaya hasil
# kustomisasi admin PASTI tersimpan dan langsung terlihat oleh semua user.
#
# Kategori: service, country, button, other, template, premium
# Tiap slot menyimpan: emoji_char (unicode biasa) DAN custom_emoji_id (opsional).
# custom_emoji_id hanya terisi jika admin/​user Premium menempel Custom Emoji
# asli Telegram (bukan sekadar unicode). Emoji yg punya ID ini akan dirender
# pakai tag <tg-emoji> Telegram — sehingga SEMUA user (gratis maupun premium)
# tetap bisa MELIHAT desain aslinya, walau hanya user Premium yang bisa
# menempelkannya saat mengetik (itu batasan Telegram, bukan batasan bot).
EMOJI_DB_FILE     = os.path.join(DATA_DIR, "custom_emoji.db")
EMOJI_CATEGORIES  = ("service", "country", "button", "other", "template", "premium")

def _emoji_db_conn():
    conn = sqlite3.connect(EMOJI_DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_emoji (
            category        TEXT NOT NULL,
            slot_key        TEXT NOT NULL,
            emoji_char      TEXT,
            custom_emoji_id TEXT,
            updated_by      TEXT,
            updated_at      TEXT,
            PRIMARY KEY (category, slot_key)
        )
    """)
    return conn

def emoji_db_load_all() -> dict:
    """Muat seluruh isi database ke dict in-memory:
       { category: { slot_key: {"char": str, "id": str|None} } }"""
    conn = _emoji_db_conn()
    try:
        out = {c: {} for c in EMOJI_CATEGORIES}
        rows = conn.execute(
            "SELECT category, slot_key, emoji_char, custom_emoji_id FROM custom_emoji"
        ).fetchall()
        for cat, key, char, cid in rows:
            out.setdefault(cat, {})[key] = {"char": char, "id": cid}
        return out
    finally:
        conn.close()

def emoji_db_set(category: str, slot_key: str, emoji_char: str, custom_emoji_id: str = None, admin_id: str = "0"):
    conn = _emoji_db_conn()
    try:
        conn.execute("""
            INSERT INTO custom_emoji (category, slot_key, emoji_char, custom_emoji_id, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, slot_key) DO UPDATE SET
                emoji_char=excluded.emoji_char,
                custom_emoji_id=excluded.custom_emoji_id,
                updated_by=excluded.updated_by,
                updated_at=excluded.updated_at
        """, (category, slot_key, emoji_char, custom_emoji_id, admin_id, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()
    if admin_id != "manual_file_edit":
        _emoji_export_to_file()

def emoji_db_reset_category(category: str):
    conn = _emoji_db_conn()
    try:
        conn.execute("DELETE FROM custom_emoji WHERE category=?", (category,))
        conn.commit()
    finally:
        conn.close()
    _emoji_export_to_file()

def emoji_db_reset_all():
    conn = _emoji_db_conn()
    try:
        conn.execute("DELETE FROM custom_emoji")
        conn.commit()
    finally:
        conn.close()
    _emoji_export_to_file()

def _emoji_migrate_from_json_once():
    """Migrasi sekali jalan dari emoji_settings.json (versi lama) ke database
    SQLite, supaya kustomisasi lama tidak hilang saat upgrade ke sistem baru."""
    if not os.path.exists(EMOJI_SETTINGS_FILE):
        return
    marker = os.path.join(DATA_DIR, ".emoji_migrated_to_db")
    if os.path.exists(marker):
        return
    try:
        old = load_json(EMOJI_SETTINGS_FILE, {})
        name_map = {
            "service_emojis":  "service",
            "country_emojis":  "country",
            "button_emojis":   "button",
            "other_emojis":    "other",
            "template_emojis": "template",
            "premium_emojis":  "premium",
        }
        for old_key, new_cat in name_map.items():
            for slot_key, char in (old.get(old_key) or {}).items():
                if char:
                    emoji_db_set(new_cat, slot_key, char, None, "migration")
        Path(marker).write_text("done")
        logger.info("✅ Migrasi emoji_settings.json -> custom_emoji.db selesai")
    except Exception as e:
        logger.error(f"Gagal migrasi emoji lama: {e}")

# ─── Custom Emoji <-> File JSON (bisa diedit manual) ───
# Database SQLite (custom_emoji.db) tetap jadi sumber utama supaya perubahan
# lewat bot PASTI tersimpan & konsisten, TAPI seluruh isinya juga selalu
# dicerminkan ke emoji_settings.json (format: {category: {slot_key: {"char":
# ..., "id": ...}}}) supaya admin bisa buka & edit file itu manual (isi emoji
# unicode ATAU custom_emoji_id langsung) lewat FTP/SSH tanpa lewat bot sama
# sekali. _EMOJI_FILE_SYNC_MARKER menyimpan salinan isi file terakhir yang
# DITULIS OLEH BOT — kalau isi file saat ini beda dari marker itu, berarti
# file baru saja diedit manual oleh admin, jadi diimpor balik ke database.
_EMOJI_FILE_SYNC_MARKER = EMOJI_SETTINGS_FILE + ".synced"

def _emoji_export_to_file():
    """Tulis seluruh isi database custom emoji saat ini ke emoji_settings.json
    supaya selalu bisa dibuka & diedit manual (termasuk custom_emoji_id)."""
    try:
        text = json.dumps(emoji_db_load_all(), ensure_ascii=False, indent=2, sort_keys=True)
        Path(EMOJI_SETTINGS_FILE).write_text(text, encoding="utf-8")
        Path(_EMOJI_FILE_SYNC_MARKER).write_text(text, encoding="utf-8")
    except Exception as e:
        logger.error(f"Gagal menulis emoji_settings.json: {e}")

def _emoji_import_from_file(data: dict):
    """Simpan isi dict {category: {slot_key: {char, id}}} dari file ke database."""
    for cat, slots in (data or {}).items():
        if cat not in EMOJI_CATEGORIES or not isinstance(slots, dict):
            continue
        for slot_key, entry in slots.items():
            if not isinstance(entry, dict):
                continue
            char = (entry.get("char") or "").strip()
            cid  = entry.get("id") or None
            if char or cid:
                emoji_db_set(cat, slot_key, char, cid, "manual_file_edit")

def _emoji_sync_file_on_startup():
    """Selaraskan emoji_settings.json <-> database tiap kali bot start.

    - Kalau file diedit manual sejak terakhir disinkron bot (isinya beda dari
      _EMOJI_FILE_SYNC_MARKER) → import isi file itu ke database, jadi
      perubahan manual admin di file langsung berlaku begitu bot start.
    - Setelah itu, file selalu ditulis ulang dari isi database terkini, jadi
      file yang bisa diedit manual itu SELALU ada dan SELALU akurat."""
    try:
        if os.path.exists(EMOJI_SETTINGS_FILE):
            current_text = Path(EMOJI_SETTINGS_FILE).read_text(encoding="utf-8")
            marker_text  = (Path(_EMOJI_FILE_SYNC_MARKER).read_text(encoding="utf-8")
                             if os.path.exists(_EMOJI_FILE_SYNC_MARKER) else None)
            if current_text != marker_text:
                try:
                    _emoji_import_from_file(json.loads(current_text))
                    logger.info("✅ emoji_settings.json (edit manual) berhasil di-import ke database")
                except Exception as e:
                    logger.error(f"emoji_settings.json gagal diparse, dilewati (cek format JSON): {e}")
        _emoji_export_to_file()
    except Exception as e:
        logger.error(f"Gagal sinkronisasi emoji_settings.json: {e}")

_emoji_migrate_from_json_once()
emoji_settings = emoji_db_load_all()
_emoji_sync_file_on_startup()
emoji_settings = emoji_db_load_all()   # reload — mungkin berubah kalau ada edit manual di file


# ─── Sinkronisasi Custom Emoji ke dict `services` & `countries` ───
# Banyak tempat di kode ini menampilkan icon service / flag negara langsung
# dari dict `services[...]['icon']` / `countries[...]['flag']` (termasuk di
# TOMBOL inline seperti pilih service/negara), bukan lewat get_svc_icon()/
# get_country_flag(). Supaya custom emoji admin OTOMATIS muncul di SEMUA
# tempat itu (termasuk tombol-tombol) tanpa perlu mengubah tiap baris satu-
# satu, kita simpan snapshot emoji default di awal, lalu setiap kali admin
# menyimpan/reset Custom Emoji, kita timpa langsung dict `services`/`countries`
# di memori dengan emoji terbaru (atau kembalikan ke default kalau direset).
_SERVICE_ICON_DEFAULTS = {sid: s.get("icon", "📞") for sid, s in services.items()}
_COUNTRY_FLAG_DEFAULTS = {cc: c.get("flag", "🌍") for cc, c in countries.items()}

def _apply_emoji_overrides():
    """Terapkan emoji_settings saat ini ke dict services & countries (in-place)."""
    svc_overrides = emoji_settings.get("service") or {}
    for sid, s in services.items():
        entry = svc_overrides.get(sid)
        if entry and entry.get("char"):
            s["icon"] = entry["char"]
        elif sid in _SERVICE_ICON_DEFAULTS:
            s["icon"] = _SERVICE_ICON_DEFAULTS[sid]
    country_overrides = emoji_settings.get("country") or {}
    for cc, c in countries.items():
        entry = country_overrides.get(cc)
        if entry and entry.get("char"):
            c["flag"] = entry["char"]
        elif cc in _COUNTRY_FLAG_DEFAULTS:
            c["flag"] = _COUNTRY_FLAG_DEFAULTS[cc]

_apply_emoji_overrides()

# ─── Default Custom Emoji ID — Premium (di-"tanam" langsung di SC) ───
# Peta ID Custom Emoji Premium bawaan untuk flag negara (key = kode dial,
# sama seperti key dict `countries`) & ikon service (key = id service, sama
# seperti key dict `services`). Dipakai supaya SEMUA slot yang BELUM PERNAH
# di-custom manual oleh admin otomatis memakai desain Custom Emoji Premium
# ini sebagai default — admin tidak perlu set satu-satu dari menu Custom
# Emoji bot. Kalau admin SUDAH pernah mengganti suatu slot (sudah ada baris
# tersimpan di database), default di bawah ini TIDAK menimpa pilihan admin.
_COUNTRY_DEFAULT_EMOJI_IDS = {
    "1": "5294355805812834147",
    "1242": "5294330091843634753",
    "1246": "5294280214388426740",
    "1268": "5294167544511349797",
    "1441": "5294427437277400427",
    "1473": "5296736811127687537",
    "1767": "5296266142841586615",
    "1784": "5294047487290537281",
    "1787": "5294043419956499702",
    "1809": "5296569105539680825",
    "1868": "5296544413772695465",
    "1876": "5294043553100481116",
    "20": "5294235727117172303",
    "211": "5294310953469362786",
    "212": "5296322948079044611",
    "213": "5294387425362068411",
    "216": "5294512524874499060",
    "218": "5293995067214678723",
    "221": "5296684816253603762",
    "223": "5294484135140676049",
    "224": "5294191196896251397",
    "225": "5293991322003200135",
    "226": "5294405481404583464",
    "227": "5296371253576224227",
    "228": "5296331181531349865",
    "229": "5296639272420397279",
    "230": "5294111851670423821",
    "231": "5294413732036764370",
    "232": "5296404427903615479",
    "233": "5294212194991359368",
    "234": "5294062227618286918",
    "235": "5294183405825577204",
    "236": "5222073662294733523",
    "237": "5294445540564551759",
    "238": "5294120815267169983",
    "239": "5294418310471899505",
    "240": "5296289125211587253",
    "241": "5296456946763711257",
    "242": "5294179115153245536",
    "243": "5294355333366435362",
    "244": "5296450534377539069",
    "245": "5296731124590986020",
    "248": "5294141555664242057",
    "249": "5294282658224816336",
    "250": "5294178784440765714",
    "251": "5296664814590904151",
    "252": "5296337366284255780",
    "253": "5294203008056313440",
    "254": "5296643232380240561",
    "255": "5294310596987079349",
    "256": "5294025488468036779",
    "257": "5294130088101561854",
    "258": "5294037939578225344",
    "260": "5296573559420766393",
    "261": "5294531783507855529",
    "263": "5294073497612471552",
    "264": "5294363360660309794",
    "266": "5294349097073920942",
    "267": "5296679391709909938",
    "268": "5296264338955322526",
    "27": "5294057760852296487",
    "298": "5296469342039327674",
    "30": "5294030651018735906",
    "31": "5294199065276335626",
    "32": "5294332763313292517",
    "33": "5294338402605354650",
    "34": "5294124040787608668",
    "350": "5280568320842553060",
    "351": "5294442353698820401",
    "352": "5294282945987631258",
    "353": "5294445119657754986",
    "354": "5296396568113463650",
    "355": "5296613073119888465",
    "356": "5296740083892766020",
    "357": "5296524180181765471",
    "358": "5294245382203657313",
    "359": "5294329219965272288",
    "36": "5294297883883884281",
    "370": "5296529823768790124",
    "371": "5294434485318733105",
    "372": "5296631361090635271",
    "373": "5296516174362724142",
    "374": "5294424778692643941",
    "375": "5294208398240269676",
    "376": "5296582230959737757",
    "377": "5296363591354570187",
    "380": "5301210178480259258",
    "381": "5294178423663510137",
    "382": "5294373621337179756",
    "383": "5294134378773888806",
    "385": "5296728624920020374",
    "386": "5294443710908482362",
    "387": "5294273286606175399",
    "389": "5294163983983462191",
    "39": "5294096883709398908",
    "40": "5296461881681135191",
    "41": "5294416459340989591",
    "420": "5294325002307388969",
    "421": "5296572940945476108",
    "43": "5296542940598914203",
    "44": "5294197287159876240",
    "45": "5294392875675567914",
    "46": "5294412516561013997",
    "47": "5296763869421650829",
    "48": "5294220982494447717",
    "49": "5296711651209267465",
    "501": "5294015025927700728",
    "502": "5294324555630788961",
    "503": "5294407199391504282",
    "504": "5294229477939757335",
    "506": "5294225414900695411",
    "507": "5296553811161139652",
    "509": "5296495086073300424",
    "51": "5294536121424824940",
    "52": "5296789308512946569",
    "53": "5199814019325646173",
    "54": "5296543610613811920",
    "55": "5296467808736004436",
    "56": "5296514988951750110",
    "57": "5294111658396895748",
    "58": "5276346818962147941",
    "591": "5296756013926466928",
    "592": "5296762207269307612",
    "593": "5296730119568638916",
    "595": "5294247589816845627",
    "597": "5294322519816293327",
    "598": "5296505905095919754",
    "60": "5294132501873182584",
    "61": "5294188899088744731",
    "62": "5294260771071476936",
    "63": "5296542068720551671",
    "64": "5294233523798954545",
    "65": "5296652067127967695",
    "66": "5294112929707215629",
    "670": "5294001707234116044",
    "673": "5293996845331138180",
    "675": "5296604938451832148",
    "677": "5296631502824555891",
    "678": "5294386927145865802",
    "679": "5294277143486811605",
    "685": "5294303252593001119",
    "686": "5294329816965727869",
    "687": "5235605674020332176",
    "691": "5294477924617963061",
    "692": "5294105774291701348",
    "7": "5296288442311788486",
    "7778": "5294048281859475822",
    "81": "5296431112535426565",
    "82": "5293985257509375078",
    "84": "5294101771382179258",
    "850": "5443117572977348988",
    "855": "5294475326162751271",
    "856": "5294425689225708603",
    "86": "5294541717767213404",
    "880": "5294438230530212180",
    "886": "5366187256937726720",
    "91": "5294495881876229590",
    "92": "5294165538761622390",
    "93": "5296313086834131752",
    "94": "5294116309846475631",
    "960": "5294397428340901802",
    "961": "5294526453453439797",
    "962": "5296499402515433610",
    "963": "5384446812180475284",
    "964": "5296720490251961770",
    "965": "5294449350200545798",
    "966": "5296440716082300772",
    "967": "5294141521304506242",
    "968": "5294203716725918231",
    "970": "5294180102995725522",
    "971": "5296750159886044083",
    "972": "5294435906952907122",
    "973": "5296574792076378414",
    "974": "5296274745661082738",
    "975": "5296691507812648381",
    "976": "5293985068530813794",
    "977": "5296678678745334353",
    "98": "5294443526224889744",
    "992": "5294223963201752433",
    "993": "5294468643193635490",
    "994": "5300875858225946690",
    "995": "5296748025287295377",
    "996": "5296272894530175743",
    "998": "5294243788770794963",
    # ↓ Migrasi dari main.py FLAG_STICKER (dicocokkan lewat emoji flag)
    "95": "5294254478944393569",
    "505": "5294240825243358100",
    "222": "5294429743674840973",
    "291": "5291922054004625949",
    "676": "5294362935458548705",
    "688": "5294263837678131580",
    "680": "5433852121634060293",
    "378": "5292183188016222701",
    "423": "5292048742654957785",
    "269": "5294351381996521508",
    "1758": "5224541228380467535",
    "1869": "5222000927023577045",
}

_SERVICE_DEFAULT_EMOJI_IDS = {
    "apple": "5334955749409834455",
    "bitget": "5373265917092316632",
    "discord": "5325612636467903082",
    "facebook": "5323261730283863478",
    "google": "5359758030198031389",
    "imo": "5334954057192719331",
    "instagram": "5319160079465857105",
    "lazada": "5229011542011299168",
    "microsoft": "5370857634440170316",
    "netflix": "5323261730283863478",
    "other": "5197645099495862838",
    "shopee": "5197645099495862838",
    "snapchat": "5330248916224983855",
    "telegram": "5330237710655306682",
    "tiktok": "5327982530702359565",
    "tinder": "5458603043203327669",
    "twitter": "5330337435500951363",
    "wechat": "5332524123610430820",
    "whatsapp": "5334998226636390258",
    "xiaomi": "5217824874487101321",
}

# ══════════════════════════════════════════════════════════════
#  SERVICE SHORT-CODE / SINGKATAN  (untuk {svc_short} placeholder)
#  Migrasi dari main.py — Contoh: WhatsApp → Wa, Facebook → Fb, dst.
# ══════════════════════════════════════════════════════════════
SVC_SHORT = {
    "WhatsApp": "Wa",   "Facebook": "Fb",   "Telegram": "Tg",  "Instagram": "Ig",
    "TikTok": "Tt",     "Google": "Gg",     "Discord": "Ds",   "Twitter": "Tw",
    "Apple": "Ap",      "Binance": "Bn",    "PayPal": "Pp",    "Microsoft": "Ms",
    "1xBet": "1x",      "ChatGPT": "Cg",    "SMS": "Sm",
    "Amazon": "Az",     "Netflix": "Nf",    "Spotify": "Sp",   "Uber": "Ub",
    "Grab": "Gr",       "Gojek": "Gj",      "Shopee": "Sh",    "Lazada": "Lz",
    "LINE": "Ln",       "WeChat": "Wc",     "Viber": "Vb",     "Signal": "Sg",
    "Snapchat": "Sc",   "LinkedIn": "Li",   "Yahoo": "Yh",     "Coinbase": "Cb",
    "OKX": "Ok",        "Bybit": "By",      "KuCoin": "Kc",    "Huobi": "Hb",
    "Bitget": "Bg",     "Steam": "St",      "Epic Games": "Ep","PlayStation": "Ps",
    "Xbox": "Xb",       "Airbnb": "Ab",     "Bolt": "Bo",      "Careem": "Cr",
    "Alipay": "Al",     "Zalo": "Za",       "Kakao": "Kk",     "Naver": "Nv",
    "Baidu": "Bd",      "Twitch": "Tc",     "Reddit": "Rd",    "Pinterest": "Pn",
    "Tinder": "Td",     "Bumble": "Bm",     "OLX": "Ox",       "eBay": "Eb",
    "Roblox": "Rx",     "Garena": "Ga",     "Free Fire": "Ff", "Mobile Legends": "Ml",
    "Payoneer": "Py",   "Skrill": "Sk",     "Revolut": "Rv",   "Wise": "Ws",
    "Grindr": "Gd",     "Threads": "Th",    "X": "X",          "Zoom": "Zm",
    "Slack": "Sl",      "Dropbox": "Db",    "Yandex": "Ya",    "Mail.ru": "Mr",
    "VK": "Vk",         "OVO": "Ov",        "DANA": "Dn",      "GoPay": "Gp",
    "Flip": "Fl",       "Dana Kaget": "Dk", "IMO": "Im",       "KakaoTalk": "Kt",
    "Xiaomi": "Xm",     "Verification": "Vr","Other": "Ot",
}

def _svc_short(service: str) -> str:
    """Ambil singkatan service untuk placeholder {svc_short}.
    Kalau tidak ada di tabel SVC_SHORT, auto-generate dari nama."""
    if not service:
        return "Sv"
    if service in SVC_SHORT:
        return SVC_SHORT[service]
    s = service.strip()
    if not s:
        return "Sv"
    words = s.split()
    if len(words) >= 2:
        return (words[0][:1] + words[1][:1]).capitalize()
    return s[:2].capitalize()

# ══════════════════════════════════════════════════════════════
#  LANGUAGE DETECTION  (untuk {language} / {lang_full} placeholder)
#  Migrasi dari main.py — deteksi bahasa isi SMS dari script Unicode-nya.
# ══════════════════════════════════════════════════════════════
LANG_DATA = {
    "EN": ("EN", "English"),    "AR": ("AR", "Arabic"),     "BN": ("BN", "Bengali"),
    "CN": ("CN", "Chinese"),    "RU": ("RU", "Russian"),    "TR": ("TR", "Turkish"),
    "FA": ("FA", "Persian"),    "HI": ("HI", "Hindi"),      "UR": ("UR", "Urdu"),
    "ID": ("ID", "Indonesian"), "MS": ("MS", "Malay"),      "TH": ("TH", "Thai"),
    "VI": ("VI", "Vietnamese"), "FR": ("FR", "French"),     "DE": ("DE", "German"),
    "ES": ("ES", "Spanish"),    "PT": ("PT", "Portuguese"), "IT": ("IT", "Italian"),
    "PL": ("PL", "Polish"),     "UK": ("UK", "Ukrainian"),  "KO": ("KO", "Korean"),
    "JA": ("JA", "Japanese"),
}

def _detect_lang(sms: str, iso: str = ""):
    """Deteksi bahasa dari isi SMS berdasarkan rentang Unicode script-nya.
    Return (lang_short, lang_full). Migrasi dari main.py."""
    sms = sms or ""
    lang_code = "EN"
    if re.search(r"[\u0600-\u06FF]", sms):
        if iso in ("PK", "AF"):        lang_code = "UR"
        elif iso == "IR":              lang_code = "FA"
        else:                          lang_code = "AR"
    elif re.search(r"[\u0980-\u09FF]", sms): lang_code = "BN"
    elif re.search(r"[\u4e00-\u9fff]", sms): lang_code = "CN"
    elif re.search(r"[\u0400-\u04FF]", sms):
        lang_code = "UK" if iso == "UA" else "RU"
    elif re.search(r"[\u0900-\u097F]", sms): lang_code = "HI"
    elif re.search(r"[\u0e00-\u0e7f]", sms): lang_code = "TH"
    elif re.search(r"[\uac00-\ud7af]", sms): lang_code = "KO"
    elif re.search(r"[\u3040-\u30ff]", sms): lang_code = "JA"
    elif re.search(r"\b(le|la|les|est|bonjour)\b", sms, re.I): lang_code = "FR"
    elif re.search(r"\b(der|die|das|ist|bitte)\b", sms, re.I): lang_code = "DE"
    return LANG_DATA.get(lang_code, (lang_code, lang_code))

def _seed_default_premium_emoji_ids():
    """Tanam default Custom Emoji ID (flag negara & ikon service) di atas ke
    database — HANYA untuk slot yang belum pernah di-custom manual oleh
    admin (belum ada baris di database untuk slot itu)."""
    global emoji_settings
    seeded = 0
    country_overrides = emoji_settings.get("country") or {}
    for cc, cid in _COUNTRY_DEFAULT_EMOJI_IDS.items():
        if cc in countries and cc not in country_overrides:
            char_default = countries[cc].get("flag", "🌍")
            emoji_db_set("country", cc, char_default, cid, "default_seed")
            seeded += 1
    service_overrides = emoji_settings.get("service") or {}
    for sid, cid in _SERVICE_DEFAULT_EMOJI_IDS.items():
        if sid in services and sid not in service_overrides:
            char_default = services[sid].get("icon", "📞")
            emoji_db_set("service", sid, char_default, cid, "default_seed")
            seeded += 1
    if seeded:
        emoji_settings = emoji_db_load_all()
        _apply_emoji_overrides()
        logger.info(f"✅ {seeded} default Custom Emoji ID (premium) berhasil ditanam ke database")

_seed_default_premium_emoji_ids()

def _emoji_slot(category: str, slot_key: str, default_char: str) -> dict:
    """Ambil entry {char, id} utk 1 slot, fallback ke default kalau belum diatur."""
    e = emoji_settings.get(category, {}).get(slot_key)
    if e and e.get("char"):
        return e
    return {"char": default_char, "id": None}

def get_svc_icon(svc_id: str) -> str:
    """Return custom icon for service if set, else default."""
    default = services.get(svc_id, {}).get("icon", "📞")
    return _emoji_slot("service", svc_id, default)["char"]

def get_country_flag(cc: str) -> str:
    """Return custom flag for country code if set, else default."""
    default = countries.get(cc, {}).get("flag", "🌍")
    return _emoji_slot("country", cc, default)["char"]

def get_btn_emoji(key: str, default: str) -> str:
    """Return custom button emoji if set, else default."""
    return _emoji_slot("button", key, default)["char"]

def get_other_emoji(key: str, default: str) -> str:
    """Return custom other emoji if set, else default."""
    return _emoji_slot("other", key, default)["char"]

def emoji_html(entry: dict) -> str:
    """Render 1 entry {char, id} sebagai HTML. Kalau entry punya custom_emoji_id
    (emoji Premium asli), pakai tag <tg-emoji> resmi Telegram supaya SEMUA user
    (gratis maupun premium) tetap melihat desain aslinya.
    Kalau hanya ada ID tanpa char (input via emoji ID langsung), gunakan ✨ sebagai
    fallback placeholder di dalam tag <tg-emoji>."""
    char = entry.get("char") or ""
    cid  = entry.get("id")
    if cid:
        # Jika char kosong (emoji diset via ID langsung), pakai placeholder ✨
        display_char = char if char else "✨"
        esc = html.escape(display_char)
        return f'<tg-emoji emoji-id="{html.escape(str(cid))}">{esc}</tg-emoji>'
    esc = html.escape(char)
    return esc

# ─── Fallback Custom Emoji Premium — GAGAL LOAD → EMOJI BIASA ───
# Kalau ID Custom Emoji Premium yang ditempel (di teks lewat <tg-emoji> atau
# di tombol lewat icon_custom_emoji_id) sudah tidak valid lagi di sisi
# Telegram (mis. dihapus/expired/ID salah), Telegram API akan MENOLAK seluruh
# pengiriman pesan (bukan cuma emoji-nya yang gagal). Tanpa penanganan khusus,
# ini bikin SELURUH pesan (termasuk OTP) gagal terkirim sama sekali. Fungsi-
# fungsi di bawah menyediakan "jaring pengaman": kalau pengiriman pertama
# gagal, otomatis coba kirim ULANG memakai emoji BIASA (karakter asli tanpa
# tag <tg-emoji> / tanpa icon_custom_emoji_id) supaya pesan tetap sampai.
_TG_EMOJI_TAG_RE = re.compile(r'<tg-emoji emoji-id="[^"]*">(.*?)</tg-emoji>', re.DOTALL)

def _strip_tg_emoji_tags(text: str) -> str:
    """Buang tag <tg-emoji emoji-id="..">X</tg-emoji> dan sisakan X (karakter
    emoji biasa) saja — dipakai sebagai fallback kalau ID custom emoji Premium
    di teks pesan sudah tidak valid lagi."""
    if not text:
        return text
    return _TG_EMOJI_TAG_RE.sub(lambda m: m.group(1), text)

def _strip_btn_icon_kwargs(reply_markup):
    """Kembalikan salinan keyboard (Inline ATAU Reply/bottom keyboard) TANPA
    icon_custom_emoji_id di tombol manapun — dipakai sebagai fallback kalau ID
    custom emoji Premium di tombol sudah tidak valid lagi. Emoji karakter di
    label tombol (yang memang selalu disertakan oleh mkbtn()/main_reply_keyboard())
    tetap tampil normal."""
    if not reply_markup:
        return reply_markup
    if getattr(reply_markup, "inline_keyboard", None):
        new_rows = []
        changed = False
        for row in reply_markup.inline_keyboard:
            new_row = []
            for btn in row:
                kw = dict(getattr(btn, "api_kwargs", None) or {})
                if "icon_custom_emoji_id" in kw:
                    kw.pop("icon_custom_emoji_id", None)
                    changed = True
                extra = {}
                if btn.callback_data is not None:
                    extra["callback_data"] = btn.callback_data
                elif btn.url is not None:
                    extra["url"] = btn.url
                elif getattr(btn, "copy_text", None) is not None:
                    extra["copy_text"] = btn.copy_text
                new_row.append(InlineKeyboardButton(btn.text, api_kwargs=kw, **extra))
            new_rows.append(new_row)
        return InlineKeyboardMarkup(new_rows) if changed else reply_markup
    if getattr(reply_markup, "keyboard", None):
        new_rows = []
        changed = False
        for row in reply_markup.keyboard:
            new_row = []
            for btn in row:
                kw = dict(getattr(btn, "api_kwargs", None) or {})
                if "icon_custom_emoji_id" in kw:
                    kw.pop("icon_custom_emoji_id", None)
                    changed = True
                new_row.append(KeyboardButton(btn.text, api_kwargs=kw))
            new_rows.append(new_row)
        if not changed:
            return reply_markup
        return ReplyKeyboardMarkup(
            new_rows,
            resize_keyboard=getattr(reply_markup, "resize_keyboard", True),
            one_time_keyboard=getattr(reply_markup, "one_time_keyboard", False),
        )
    return reply_markup

def _is_emoji_related_error(exc: Exception) -> bool:
    """Deteksi kasar apakah error dari Telegram kemungkinan disebabkan oleh
    Custom Emoji Premium yang gagal dimuat/invalid (bukan error lain seperti
    chat not found / bot diblokir user, dsb — supaya kita tidak mengulang
    pengiriman percuma untuk error yang jelas tidak berhubungan dengan emoji)."""
    msg = str(exc).upper()
    keywords = (
        "CUSTOM_EMOJI", "EMOJI_ID", "STICKERSET", "ENTITIES_INVALID",
        "ENTITY", "PARSE", "BAD REQUEST",
    )
    return any(k in msg for k in keywords)

async def safe_send_message(bot, chat_id, text, parse_mode="HTML", reply_markup=None, **kwargs):
    """Pengganti bot.send_message() yang aman terhadap Custom Emoji Premium
    gagal load. Kalau pengiriman pertama gagal DAN errornya terlihat terkait
    emoji/parsing, otomatis kirim ulang dengan emoji BIASA (tanpa <tg-emoji>
    dan tanpa icon_custom_emoji_id) supaya pesan tetap terkirim."""
    try:
        return await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        logger.warning(f"⚠️ Kirim pesan dgn custom emoji premium gagal ({e}) — coba ulang pakai emoji biasa.")
        fallback_text   = _strip_tg_emoji_tags(text) if parse_mode == "HTML" else text
        fallback_markup = _strip_btn_icon_kwargs(reply_markup)
        return await bot.send_message(chat_id, fallback_text, parse_mode=parse_mode, reply_markup=fallback_markup, **kwargs)

async def safe_bot_edit_message_text(bot, chat_id, message_id, text, parse_mode="HTML", reply_markup=None, **kwargs):
    """Sama seperti safe_send_message(), tapi untuk bot.edit_message_text()
    (dipakai mis. Live Timeline yang push-update lewat chat_id+message_id
    langsung, bukan lewat objek `query`)."""
    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
                                            parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
    except Exception as e:
        if "not modified" in str(e).lower():
            return None
        if not _is_emoji_related_error(e):
            raise
        logger.warning(f"⚠️ Edit pesan (bot.edit_message_text) dgn custom emoji premium gagal ({e}) — coba ulang pakai emoji biasa.")
        fallback_text   = _strip_tg_emoji_tags(text) if parse_mode == "HTML" else text
        fallback_markup = _strip_btn_icon_kwargs(reply_markup)
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=fallback_text,
                                            parse_mode=parse_mode, reply_markup=fallback_markup, **kwargs)

# ─── Varian HTML dari getter emoji di atas — dipakai di pesan/tombol yang
# dikirim dengan parse_mode="HTML". Kalau slotnya punya custom_emoji_id (hasil
# admin/​user Premium MENEMPEL Custom Emoji asli), hasilnya dibungkus tag
# <tg-emoji> supaya SEMUA user (gratis maupun premium) melihat desain aslinya
# — bukan cuma placeholder karakternya. Kalau tidak ada id, sama saja dengan
# versi non-HTML (char biasa, di-escape supaya aman disisipkan ke HTML). ───

def get_svc_icon_html(svc_id: str) -> str:
    default = services.get(svc_id, {}).get("icon", "📞")
    return emoji_html(_emoji_slot("service", svc_id, default))

def get_country_flag_html(cc: str) -> str:
    default = countries.get(cc, {}).get("flag", "🌍")
    return emoji_html(_emoji_slot("country", cc, default))

def get_btn_emoji_html(key: str, default: str) -> str:
    return emoji_html(_emoji_slot("button", key, default))

def get_other_emoji_html(key: str, default: str) -> str:
    return emoji_html(_emoji_slot("other", key, default))

def get_template_emoji_html(key: str, default: str) -> str:
    return emoji_html(_emoji_slot("template", key, default))

def get_svc_icon_id(svc_id: str) -> str:
    """Return the raw custom_emoji_id for a service icon, if any (else None).
    Used to attach <code>icon_custom_emoji_id</code> on inline buttons."""
    default = services.get(svc_id, {}).get("icon", "📞")
    return _emoji_slot("service", svc_id, default).get("id")

def get_btn_emoji_id(key: str, default: str) -> str:
    """Return the raw custom_emoji_id for a button emoji slot, if any."""
    return _emoji_slot("button", key, default).get("id")

def get_country_flag_id(cc: str) -> str:
    """Return the raw custom_emoji_id for a country flag slot, if any."""
    default = countries.get(cc, {}).get("flag", "🌍")
    return _emoji_slot("country", cc, default).get("id")

def get_other_emoji_id(key: str, default: str) -> str:
    """Return the raw custom_emoji_id for an 'other' emoji slot, if any."""
    return _emoji_slot("other", key, default).get("id")

def _icon_txt(char: str, eid) -> str:
    """Return the emoji char for a button label ONLY if there's no
    custom_emoji_id — kalau eid ada, Telegram akan menampilkan ikon custom
    emoji ASLI lewat icon_custom_emoji_id, jadi karakternya tidak perlu (dan
    tidak boleh) ditulis lagi di teks supaya tidak tampil DOBEL."""
    return "" if eid else (char or "")


def _make_btn_kwargs(style: str, emoji_id: str = None) -> dict:
    """Build api_kwargs dict for InlineKeyboardButton / KeyboardButton.
    Includes icon_custom_emoji_id when an emoji ID is available — this makes
    the premium custom emoji icon visible to ALL users (free + premium)."""
    kw = {"style": style}
    if emoji_id:
        kw["icon_custom_emoji_id"] = emoji_id
    return kw


def mkbtn(slot_key: str, label: str, callback_data: str = None, url: str = None,
          copy_text=None, style: str = "primary", auto_icon: bool = True):
    """Universal InlineKeyboardButton builder with automatic custom emoji ID.

    Looks up the admin-configured custom emoji for *slot_key*, attaches
    icon_custom_emoji_id in api_kwargs so the premium icon is visible to
    ALL users (not only Telegram Premium members), and falls back gracefully
    to the default emoji when no custom ID has been set.

    Set auto_icon=False untuk tombol yang LABEL-nya sudah berisi emoji manual
    sendiri (mis. f"🔐 Verification ..."). Kalau tidak, slot_key ini bisa
    ditempel custom emoji lewat menu admin Custom Emoji > Emoji Tombol/Lainnya
    (yang menerima key APAPUN, bukan cuma yang tertera di daftar bawaan),
    sehingga ikon slot itu nempel DI ATAS emoji manual yang sudah ada di teks
    → tampil dobel. auto_icon=False memastikan tombol ini murni pakai emoji
    manual di teksnya saja, tidak pernah nempel ikon kedua.

    Usage:
        mkbtn("balance_btn", "Balance", callback_data="profil_balance", style="success")
        mkbtn("copy_all",   "Copy All Numbers", copy_text=CopyTextButton(text=txt))
    """
    if not auto_icon:
        kw = {"style": style}
        extra = {}
        if callback_data is not None:
            extra["callback_data"] = callback_data
        elif url is not None:
            extra["url"] = url
        elif copy_text is not None:
            extra["copy_text"] = copy_text
        return InlineKeyboardButton(label, api_kwargs=kw, **extra)

    default_emoji = _BUTTON_EMOJI_DEFAULTS.get(slot_key, "")
    emoji_char    = get_btn_emoji(slot_key, default_emoji)
    emoji_id      = get_btn_emoji_id(slot_key, default_emoji)
    # Kalau slot ini punya custom_emoji_id, Telegram akan menampilkan ikon
    # custom emoji ASLI di tombol lewat icon_custom_emoji_id — jadi karakter
    # emoji TIDAK boleh ditempel lagi di teks, kalau tidak akan tampil DOBEL
    # (ikon custom emoji + karakter emoji di teks). Cukup pakai yang terbaru:
    # kalau emoji_id ada → hanya ikon (tanpa char di teks). Kalau tidak ada
    # (belum diset / dihapus) → fallback ke karakter biasa di teks, sama
    # persis seperti _menu_label_text() untuk menu bawah.
    text = label if emoji_id else (f"{emoji_char} {label}".strip() if emoji_char else label)
    kw   = _make_btn_kwargs(style, emoji_id)
    extra = {}
    if callback_data is not None:
        extra["callback_data"] = callback_data
    elif url is not None:
        extra["url"] = url
    elif copy_text is not None:
        extra["copy_text"] = copy_text
    return InlineKeyboardButton(text, api_kwargs=kw, **extra)


# ─── Telegram entity offsets are UTF-16 code units; Python strings are code-point
#    indexed, so multi-unit emoji (most of them, especially Custom Emoji) need
#    manual UTF-16 slicing to correctly figure out which emoji sits on which
#    line of a multi-line bulk-edit message. ───

def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2

def _utf16_slice(s: str, offset: int, length: int) -> str:
    b = s.encode("utf-16-le")
    return b[offset * 2:(offset + length) * 2].decode("utf-16-le", errors="ignore")

def _extract_custom_emojis(message) -> list:
    """Ekstrak semua custom emoji dari sebuah Message PTB.

    Return list of dict: [{"char": str, "id": str}, ...]
    — diurutkan berdasarkan offset, jadi elemen pertama = emoji pertama di teks.

    Menangani:
    • message.text  + message.entities        (pesan teks biasa)
    • message.caption + message.caption_entities  (caption foto/video)

    Menggunakan _utf16_slice agar karakter emoji yang diekstrak SELALU benar,
    karena MessageEntity.offset/length adalah UTF-16 code unit, bukan code point.
    """
    text = message.text or message.caption or ""
    entities = list(message.entities or []) + list(message.caption_entities or [])
    result = []
    for ent in entities:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            char = _utf16_slice(text, ent.offset, ent.length)
            if not char:
                char = "✨"   # fallback kalau slice gagal
            result.append({"char": char, "id": str(ent.custom_emoji_id)})
    return result

# ─── Format ketik manual: `Emoji=<id>` (mis. `Emoji=5393939933`) ───
# Alternatif dari paste Custom Emoji asli — dipakai kalau admin cuma punya
# ID-nya (angka ≥10 digit) tanpa emoji aslinya untuk ditempel. Case-insensitive,
# boleh ada/tanpa spasi di sekitar "=".
_EMOJI_TYPED_RE = re.compile(r'\bemoji\s*=\s*(\d{10,})\b', re.IGNORECASE)

def _auto_attach_premium_emoji(tmpl: dict, message) -> tuple:
    """Kalau admin PASTE template JSON yang di dalamnya mengandung Custom Emoji
    Telegram Premium (ditempel langsung di teks pesan ATAU di label tombol),
    otomatis tangkap custom_emoji_id-nya dari entity Telegram pesan itu dan
    tempelkan kembali ke template — supaya emoji itu TETAP tampil dengan
    desain aslinya untuk SEMUA user (gratis maupun Premium), tanpa perlu
    di-setting manual lewat menu 🎨 Custom Emoji.

    Selain paste langsung, admin JUGA bisa cukup KETIK ID emoji-nya saja
    dengan format `Emoji=<id>` (mis. `Emoji=5393939933`, ID minimal 10 digit,
    case-insensitive) — baik di key "text" maupun di label tombol. Berguna
    kalau admin sudah tahu/punya ID emoji tapi tidak punya emoji aslinya
    untuk ditempel. Kedua cara ini bisa dicampur bebas dalam satu template.

    • Di key "text": tiap kemunculan karakter emoji (hasil paste) ATAU pola
      `Emoji=<id>` (hasil ketik) dibungkus/diganti tag <tg-emoji emoji-id="...">
      supaya dirender lewat parse_mode HTML.
    • Di label tombol ("buttons[].label"): tombol Telegram TIDAK bisa
      menampilkan tag HTML, jadi ID-nya disimpan di key "icon_id" tombol
      tsb (dipakai _btn_style saat render) dan karakter/teks emoji-nya
      dibuang dari label supaya tidak dobel dengan icon.

    1 emoji = 1 ID (tidak boleh dobel/nyangkut):
    • Kalau 1 karakter emoji yang sama muncul beberapa kali dalam SATU paste
      dengan ID berbeda, yang dipakai adalah kemunculan PALING BARU (bukan
      yang pertama) — ID lama otomatis kalah/ketimpa.
    • Pemetaan char → ID ini JUGA disimpan ke database Custom Emoji (kategori
      "template", slot_key = karakter emoji itu sendiri). Primary key di
      database adalah (kategori, slot_key), jadi kalau nanti karakter yang
      SAMA di-upload ulang dengan ID BARU (di template ini atau template lain,
      kapan pun), baris lamanya otomatis DIGANTI (ON CONFLICT DO UPDATE) —
      ID lama otomatis hilang, tidak pernah ada 2 ID untuk 1 emoji yang sama.
      (Untuk yang diketik manual, tidak ada karakter asli untuk dipetakan ke
      database global — ID-nya langsung ditempel ke template ini saja.)

    Return (tmpl, jumlah_emoji_premium_terdeteksi — paste + ketik manual).
    """
    global emoji_settings
    customs = _extract_custom_emojis(message)
    # Overwrite (bukan setdefault) — kemunculan paling akhir yang menang kalau
    # ada karakter sama dengan ID berbeda dalam satu paste.
    emoji_map = {}
    for c in customs:
        if c["char"]:
            emoji_map[c["char"]] = c["id"]

    txt = tmpl.get("text", "")
    for char, cid in emoji_map.items():
        if char in txt:
            tag = f'<tg-emoji emoji-id="{html.escape(cid)}">{html.escape(char)}</tg-emoji>'
            txt = txt.replace(char, tag)

    # Ketik manual: `Emoji=<id>` → <tg-emoji emoji-id="id">✨</tg-emoji>
    # (pakai "✨" sebagai placeholder karena tidak ada karakter emoji asli
    # untuk kasus ini — <tg-emoji> tetap menampilkan desain asli dari ID-nya).
    typed_count = 0
    def _typed_sub(m):
        nonlocal typed_count
        typed_count += 1
        cid = m.group(1)
        return f'<tg-emoji emoji-id="{html.escape(cid)}">✨</tg-emoji>'
    txt = _EMOJI_TYPED_RE.sub(_typed_sub, txt)
    tmpl["text"] = txt

    for b in tmpl.get("buttons", []):
        label = b.get("label", "")
        if not label:
            continue
        for char, cid in emoji_map.items():
            if char in label:
                b["icon_id"] = cid
                label = label.replace(char, "").strip()
        m = _EMOJI_TYPED_RE.search(label)
        if m:
            b["icon_id"] = m.group(1)
            label = _EMOJI_TYPED_RE.sub("", label).strip()
            typed_count += 1
        b["label"] = label

    # Simpan ke database global (kategori "template") supaya 1 emoji tetap
    # cuma terikat ke 1 ID — upload baru utk karakter yang sama otomatis
    # menimpa ID lamanya. (Hanya untuk hasil paste, yang punya karakter asli.)
    for char, cid in emoji_map.items():
        emoji_db_set("template", char, char, cid, "auto_template_paste")
    if emoji_map:
        emoji_settings = emoji_db_load_all()
        _apply_emoji_overrides()

    return tmpl, len(emoji_map) + typed_count

# ─── Count all available numbers ───
def count_total_available_numbers() -> int:
    total = 0
    for cc_dict in numbers_by_cs.values():
        for svc_list in cc_dict.values():
            total += len(svc_list)
    return total

numbers_by_cs = {}

def load_numbers():
    global numbers_by_cs
    numbers_by_cs = {}
    if not os.path.exists(NUMBERS_FILE):
        return
    try:
        with open(NUMBERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        num, cc, svc = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    elif len(parts) == 2:
                        num, cc, svc = parts[0].strip(), parts[1].strip(), "other"
                    else:
                        continue
                else:
                    num = line
                    cc  = get_country_code_from_number(num)
                    svc = "other"
                if not re.match(r"^\d{10,15}$", num):
                    continue
                if not cc:
                    continue
                numbers_by_cs.setdefault(cc, {}).setdefault(svc, [])
                if num not in numbers_by_cs[cc][svc]:
                    numbers_by_cs[cc][svc].append(num)
        total = sum(len(nums) for cc in numbers_by_cs.values() for nums in cc.values())
        logger.info(f"✅ Loaded {total} numbers")
    except Exception as e:
        logger.error(f"Error loading numbers: {e}")

def save_numbers():
    try:
        lines = []
        for cc, svcs in numbers_by_cs.items():
            for svc, nums in svcs.items():
                for num in nums:
                    lines.append(f"{num}|{cc}|{svc}")
        with open(NUMBERS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        logger.error(f"Error saving numbers: {e}")

load_numbers()

# ─── Nomor "used this cycle" tracker (untuk random cycling get number) ───
# Struktur: { cc: { svc: [num, num, ...] } }  -> nomor yang SUDAH pernah ditampilkan
# dalam siklus berjalan. Nomor TIDAK dihapus dari numbers_by_cs saat diambil user,
# supaya nomor tetap bisa dipakai lagi selama belum dihapus admin.
numbers_used_cycle = load_json(NUMBERS_CYCLE_FILE, {})

def save_numbers_cycle():
    save_json(NUMBERS_CYCLE_FILE, numbers_used_cycle)

async def async_save_numbers_cycle():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_numbers_cycle)

def save_settings():    save_json(SETTINGS_FILE, settings)

# ─── Feature On/Off Helpers ───
FEATURE_LIST = [
    ("getnumber", "☎️ Get Number"),
    ("getfile",   "📄 Get File"),
    ("cariotp",   "🔍 Cari OTP"),
    ("livetraffic", "🔥 Live Traffic"),
    ("livetimeline", "📡 Live Timeline"),
    ("tempmail",  "📧 Tempmail"),
    ("twofa",     "🔐 2FA"),
    ("balance",   "💰 Balance"),
    ("withdraw",  "💸 Withdraw"),
    ("referral",  "👥 Referral"),
    ("support",   "💬 Support"),
    ("cek_bio_wa", "🔵 Cek Bio WA"),
]

def is_feature_enabled(key: str) -> bool:
    if key == "withdraw":
        return settings.get("withdrawEnabled", True)
    return settings.get("featureToggles", {}).get(key, True)

def set_feature_enabled(key: str, value: bool):
    if key == "withdraw":
        settings["withdrawEnabled"] = value
    else:
        settings.setdefault("featureToggles", {})
        settings["featureToggles"][key] = value
    save_settings()

def feature_disabled_text(label: str, uid: str = "0") -> str:
    lang = get_user_lang(str(uid))
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    tmpl = lang_dict.get("feature_disabled") or TRANSLATIONS["en"]["feature_disabled"]
    return md2html(tmpl.format(feature=html.escape(str(label))))
def save_referrals():   save_json(REFERRALS_FILE, referrals)

async def safe_edit(query, text, **kwargs):
    """Edit pesan dengan aman. Selain menahan error "message is not modified",
    fungsi ini sekarang JUGA otomatis fallback ke emoji biasa (tanpa
    <tg-emoji>/icon_custom_emoji_id) kalau editnya gagal karena Custom Emoji
    Premium yang sudah tidak valid — dipakai di HAMPIR SEMUA menu/tombol bot
    ini, jadi 1 perbaikan di sini otomatis melindungi semua pemanggilnya."""
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception as e:
        if "not modified" in str(e).lower():
            return
        if _is_emoji_related_error(e):
            logger.warning(f"⚠️ Edit pesan dgn custom emoji premium gagal ({e}) — coba ulang pakai emoji biasa.")
            fb_kwargs = dict(kwargs)
            fb_text   = _strip_tg_emoji_tags(text) if fb_kwargs.get("parse_mode") == "HTML" else text
            if "reply_markup" in fb_kwargs:
                fb_kwargs["reply_markup"] = _strip_btn_icon_kwargs(fb_kwargs["reply_markup"])
            try:
                await query.edit_message_text(fb_text, **fb_kwargs)
                return
            except Exception as e2:
                if "not modified" in str(e2).lower():
                    return
                raise
        else:
            raise

async def async_save_numbers():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_numbers)

async def async_save_users():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_users)

async def async_save_active():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_active)

async def async_save_otp_log():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_otp_log)

async def async_save_earnings():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_earnings)

async def async_save_withdrawals():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_withdrawals)

async def async_save_referrals():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_referrals)

def save_users():       save_json(USERS_FILE, users)
def save_active():
    save_json(ACTIVE_NUMBERS_FILE, active_numbers)
    rebuild_suffix_index()
def save_otp_log():     save_json(OTP_LOG_FILE, otp_log[-20000:])
def save_admins():      save_json(ADMINS_FILE, admins)
def save_totp():        save_json(TOTP_SECRETS_FILE, totp_secrets)
def save_temp_mails():  save_json(TEMP_MAILS_FILE, temp_mails)
def save_earnings():    save_json(EARNINGS_FILE, earnings)
def save_withdrawals(): save_json(WITHDRAW_FILE, withdrawals)
def save_cp():          save_json(COUNTRY_PRICES_FILE, country_prices)
def save_countries():   save_json(COUNTRIES_FILE, countries)
def save_services():    save_json(SERVICES_FILE, services)
# NOTE: custom emoji sudah tidak pakai save_json lagi — setiap perubahan
# langsung ditulis ke database SQLite lewat emoji_db_set()/emoji_db_reset_*().

if not os.path.exists(SETTINGS_FILE):
    save_settings()
if not os.path.exists(COUNTRIES_FILE):
    save_countries()
if not os.path.exists(SERVICES_FILE):
    save_services()

def is_owner(user_id: str) -> bool:
    return str(user_id) in OWNER_IDS

def is_admin(user_id: str) -> bool:
    return str(user_id) in OWNER_IDS or str(user_id) in admins

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str, exclude_uid: str = None):
    """Kirim notifikasi ke semua admin (kecuali admin yang barusan melakukan aksi)."""
    for admin_uid in list(admins):
        if exclude_uid and str(admin_uid) == str(exclude_uid):
            continue
        try:
            await context.bot.send_message(int(admin_uid), text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"notify_admins error uid={admin_uid}: {e}")

async def broadcast_stock_notify(
    context: ContextTypes.DEFAULT_TYPE,
    svc_id: str,
    cc_counts: dict,   # {cc: count}
    total: int,
    total_all: int = 0,   # grand total available after upload
    text: str = None,  # legacy fallback (ignored)
):
    """Send stock notification to ALL users when admin uploads numbers.
    Runs as background task so it does not block the admin.
    Only runs when settings['stockNotifyUsers'] is enabled.
    Layout: clean single notify, Get Number (top) + Get File (bottom) buttons."""
    if not settings.get("stockNotifyUsers", False):
        return

    # Pakai varian *_html supaya Custom Emoji Premium (svc icon / flag / tombol)
    # tampil sebagai desain asli lewat <tg-emoji> untuk SEMUA user, bukan
    # cuma placeholder karakternya.
    svc_icon_html = get_svc_icon_html(svc_id)
    svc_info = services.get(svc_id, {"icon": "📞", "name": svc_id})

    sent = 0
    for target_uid in list(users.keys()):
        try:
            lang = get_user_lang(target_uid)
            tr = TRANSLATIONS[lang]

            # Build country lines with custom flags
            country_lines = []
            for cc, cnt in cc_counts.items():
                flag_html = get_country_flag_html(cc)
                cname = html.escape(str(countries.get(cc, {"name": cc}).get("name", cc)))
                country_lines.append(
                    f"  {flag_html} {cname} — <b>{cnt}</b> {html.escape(tr['notify_numbers_unit'])}"
                )
            country_text = "\n".join(country_lines) if country_lines else ""

            notify_title = tr.get('notify_title', '🎉 New Numbers Available!').replace('*', '')
            msg = (
                f"{get_other_emoji_html('notify', '🎉')} <b>{html.escape(notify_title)}</b>\n\n"
                f"{html.escape(tr['notify_service_label'])} {svc_icon_html} <b>{html.escape(str(svc_info['name']))}</b>\n"
            )
            if country_text:
                msg += f"{html.escape(tr['notify_country_label'])}\n{country_text}\n"
            msg += f"{html.escape(tr['notify_total_label'])} <b>{total}</b> {html.escape(tr['notify_numbers_unit'])}"
            if total_all > 0:
                total_lbl = "📊 <b>Total Tersedia:</b>" if lang == "id" else "📊 <b>Total Available:</b>"
                msg += f"\n{total_lbl} <b>{total_all}</b> {html.escape(tr['notify_numbers_unit'])}"
            msg += f"\n\n{html.escape(tr['notify_hurry'])}"

            # Buttons: Get Number on top, Get File below (vertical layout).
            # Tempelkan juga icon_custom_emoji_id kalau slotnya punya emoji Premium.
            get_num_label = get_btn_emoji("get_number", "☎️") + " " + tr.get("notify_get_number", "Get Number")
            get_file_label = get_btn_emoji("get_file", "📁") + " " + tr.get("notify_get_file", "Get File")
            get_num_id  = get_btn_emoji_id("get_number", "☎️")
            get_file_id = get_btn_emoji_id("get_file", "📁")
            num_style  = {"style": "success"}
            file_style = {"style": "primary"}
            if get_num_id:
                num_style["icon_custom_emoji_id"] = get_num_id
            if get_file_id:
                file_style["icon_custom_emoji_id"] = get_file_id
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_num_label,  callback_data="back_services",    api_kwargs=num_style)],
                [InlineKeyboardButton(get_file_label, callback_data="fileback_services", api_kwargs=file_style)],
            ])
            await safe_send_message(context.bot, int(target_uid), msg, parse_mode="HTML", reply_markup=kb)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    logger.info(f"📢 Stock notify broadcast sent to {sent} users (svc={svc_id}, new={total}, total_all={total_all}).")

def get_country_code_from_number(num: str) -> str:
    s = str(num)
    for l in [3, 2, 1]:
        if s[:l] in countries:
            return s[:l]
    return ""

def get_otp_price(cc: str) -> float:
    return country_prices.get(cc, settings.get("defaultOtpPrice", 0.25))

def get_user_earnings(uid: str) -> dict:
    uid = str(uid)
    if uid not in earnings:
        earnings[uid] = {
            "balance": 0,
            "totalEarned": 0,
            "otpCount": 0,
            "referralEarnings": 0,
        }
    if "referralEarnings" not in earnings[uid]:
        earnings[uid]["referralEarnings"] = 0
    return earnings[uid]

def get_referral_link(uid: str, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start=ref_{uid}"

async def add_earning(uid: str, cc: str) -> float:
    uid = str(uid)
    price = get_otp_price(cc)
    e = get_user_earnings(uid)
    e["balance"]     = round(e["balance"] + price, 2)
    e["totalEarned"] = round(e["totalEarned"] + price, 2)
    e["otpCount"]    = e.get("otpCount", 0) + 1

    referrer_id = users.get(uid, {}).get("referredBy")
    if referrer_id and str(referrer_id) != uid:
        commission_pct = settings.get("referralCommission", 10) / 100
        commission = round(price * commission_pct, 4)
        commission = round(commission, 2)
        if commission > 0:
            re_ = get_user_earnings(str(referrer_id))
            re_["balance"]          = round(re_["balance"] + commission, 2)
            re_["totalEarned"]      = round(re_["totalEarned"] + commission, 2)
            re_["referralEarnings"] = round(re_.get("referralEarnings", 0) + commission, 2)
            logger.info(f"💸 Referral commission {commission:.2f} USD → uid={referrer_id} (from uid={uid})")

    await async_save_earnings()
    return price

def get_time_ago(dt_str: str) -> str:
    try:
        if not dt_str:
            return "unknown"
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Timestamp naive di bot ini disimpan dalam WIB (lihat now_wib()),
            # bukan UTC — sebelumnya di sini salah diasumsikan UTC, bikin
            # "time ago" meleset 7 jam.
            dt = dt.replace(tzinfo=WIB)
        now = datetime.now(WIB)
        secs = int((now - dt).total_seconds())
        if secs < 0:    return "just now"
        if secs < 60:   return f"{secs} seconds ago"
        if secs < 3600: return f"{secs // 60} minutes ago"
        if secs < 86400:return f"{secs // 3600} hours ago"
        return f"{secs // 86400} days ago"
    except Exception as e:
        logger.warning(f"get_time_ago error for '{dt_str}': {e}")
        return "unknown"

def get_available_countries_for_service(svc: str) -> list:
    return [cc for cc, svcs in numbers_by_cs.items()
            if svc in svcs and svcs[svc] and cc in countries]

async def get_multiple_numbers(cc: str, svc: str, uid: str, count: int) -> list:
    """Ambil <code>count</code> nomor secara ACAK dari stok cc/svc.

    Aturan:
    - Pilih secara acak (random.shuffle).
    - Nomor yang SEDANG aktif di user lain (ada di active_numbers dengan userId berbeda)
      dilewati dulu selama masih ada nomor lain yang tersedia.
    - Kalau semua nomor sedang aktif (stok habis), ambil dari seluruh pool lagi
      (reset siklus) — tetap acak.
    - Nomor TIDAK dihapus dari master pool (numbers_by_cs); hanya active_numbers
      yang diperbarui.
    """
    pool = numbers_by_cs.get(cc, {}).get(svc, [])
    if not pool:
        return []

    pool_set = list(pool)

    # Nomor yang sedang dipegang user LAIN (bukan user ini sendiri)
    blocked = {n for n, info in active_numbers.items()
               if info.get("userId") != str(uid)}

    available = [n for n in pool_set if n not in blocked]

    if not available:
        # Semua nomor sedang aktif di user lain → reset: ambil dari seluruh pool
        available = list(pool_set)

    random.shuffle(available)
    nums = available[:count]

    now = datetime.now(timezone.utc).isoformat()
    for n in nums:
        active_numbers[n] = {
            "userId": str(uid), "countryCode": cc, "service": svc,
            "assignedAt": now, "lastOTP": None, "otpCount": 0
        }
    save_active()
    await async_save_active()
    return nums

def extract_phone_from_text(text: str):
    m = re.search(r"\+?(\d{10,15})", text)
    return m.group(1) if m else None

# ─── Fast suffix index for active number matching ───
_suffix_index: dict = {}  # { last_8_digits: number }

def rebuild_suffix_index():
    global _suffix_index
    _suffix_index = {}
    for n in active_numbers:
        clean = n.lstrip("0")
        for l in [8, 7, 6]:
            if len(clean) >= l:
                key = clean[-l:]
                if key not in _suffix_index:
                    _suffix_index[key] = n

def guess_cc_from_number(num: str) -> str:
    """Tebak kode negara (key di `countries`, mis. '880', '62') dari awalan
    nomor E.164 — dipakai sebagai FALLBACK saat nomor tidak/belum ada di
    active_numbers (mis. OTP untuk nomor yang belum di-assign ke siapapun,
    atau sudah di-clear). Tanpa ini, cc jadi string kosong dan flag negara
    di notifikasi grup jatuh ke default 🌍 (globe) walau nomornya jelas
    kelihatan negaranya dari awalan digitnya."""
    best = ""
    for code in countries.keys():
        if num.startswith(code) and len(code) > len(best):
            best = code
    return best

def find_active_number(panel_number: str):
    """Panel এর number দিয়ে active_numbers এ fast match করো"""
    clean = re.sub(r"\D", "", panel_number).lstrip("0")
    # Direct match
    if clean in active_numbers:
        return clean
    # Suffix match via index
    for l in [8, 7, 6]:
        if len(clean) >= l:
            key = clean[-l:]
            if key in _suffix_index:
                return _suffix_index[key]
    return None

# ─── Dedup OTP kembar dalam window singkat (default 10 detik) ───
# Kalau OTP yang SAMA (nomor + kode) masuk lagi dalam waktu berdekatan (mis.
# sumber yang sama posting dobel, atau kepancing dari 2 jalur berbeda
# hampir bersamaan), cuma tampilkan/kirim SATU kali saja.
OTP_DUPLICATE_WINDOW_SECONDS = 10
_recent_otp_seen: dict = {}  # {(phone_number, otp_code): last_seen_unix_ts}

def _is_duplicate_otp(number: str, otp_code, mark: bool = True) -> bool:
    if not otp_code:
        return False
    key = (str(number), str(otp_code))
    now_ts = time.time()
    last_ts = _recent_otp_seen.get(key)
    is_dup = last_ts is not None and (now_ts - last_ts) < OTP_DUPLICATE_WINDOW_SECONDS
    if not is_dup and mark:
        _recent_otp_seen[key] = now_ts
    if len(_recent_otp_seen) > 5000:
        cutoff = now_ts - OTP_DUPLICATE_WINDOW_SECONDS
        for k, v in list(_recent_otp_seen.items()):
            if v < cutoff:
                _recent_otp_seen.pop(k, None)
    return is_dup


def _panel_history_number(value) -> str:
    """Normalize panel/history phone values for persistent deduplication."""
    return re.sub(r"\D", "", str(value or "")).lstrip("0")


def _panel_otp_in_history(number: str, otp_code) -> bool:
    """Return True when this exact number + OTP already exists in otp_log."""
    if not otp_code:
        return False
    number_key = _panel_history_number(number)
    otp_key = re.sub(r"[\s-]+", "", str(otp_code)).strip()
    if not number_key or not otp_key:
        return False
    for record in reversed(otp_log):
        if not isinstance(record, dict):
            continue
        if (
            _panel_history_number(record.get("phoneNumber")) == number_key
            and re.sub(r"[\s-]+", "", str(record.get("otpCode") or "")).strip() == otp_key
        ):
            return True
    return False


def _latest_panel_rows(rows, limit: int = PANEL_LATEST_ROWS_LIMIT) -> list:
    """Keep only the newest panel rows, preserving fetch order as fallback."""
    if not isinstance(rows, (list, tuple)):
        return []
    candidates = [
        row for row in rows
        if isinstance(row, (list, tuple)) and len(row) >= 6
    ]
    if len(candidates) <= limit:
        return list(candidates)

    parsed = []
    for index, row in enumerate(candidates):
        parsed_ts = _parse_panel_ts(row[0])
        parsed.append((parsed_ts, index, row))

    if any(item[0] is not None for item in parsed):
        parsed.sort(
            key=lambda item: (
                item[0] is not None,
                item[0].timestamp() if item[0] is not None else 0,
                -item[1],
            ),
            reverse=True,
        )
        return [item[2] for item in parsed[:limit]]

    # All panel formats that do not expose a parseable timestamp already
    # return the newest records first.
    return candidates[:limit]

def extract_otp(text: str):
    cleaned = re.sub(r'\b(19|20)\d{2}[-/]\d{2}[-/]\d{2}(?:[T\s]\d{2}:\d{2}:\d{2})?\b', '', text)
    cleaned = re.sub(r'\b(19|20)\d{2}\b', '', cleaned)
    patterns = [
        r'OTP\s*Code[:\s]+(\d{4,8})',
        r'\b[A-Z]-(\d{4,8})\b',
        r'(?:otp|code|pin|verification|verify|token)[^\d]{0,10}(\d{4,8})',
        r'(?:is|has|:)\s*(\d{4,8})\b',
        r'\b(\d{6})\b',
        r'\b(\d{4})\b',
    ]
    for p in patterns:
        m = re.search(p, cleaned, re.IGNORECASE)
        if m and 4 <= len(m.group(1)) <= 8:
            return m.group(1)
    return None

# ─── Cari OTP (search by number / last digits, within admin-configured window) ───
def format_time_ago(iso_ts: str) -> str:
    try:
        ts = datetime.fromisoformat(iso_ts)
    except Exception:
        return "?"
    now = datetime.now(ts.tzinfo) if ts.tzinfo else now_wib()
    delta = now - ts
    secs = int(delta.total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"{secs} detik"
    mins = secs // 60
    if mins < 60:
        return f"{mins} menit"
    hours = mins // 60
    if hours < 24:
        return f"{hours} jam"
    days = hours // 24
    return f"{days} hari"

# ─── Cari OTP Scope (Bot / Grup / Semua) ───
OTP_SCOPE_ORDER = ["bot", "group", "all"]
OTP_SCOPE_LABELS = {
    "bot":   "🤖 Bot Saja (Private Chat)",
    "group": "👥 Grup Saja",
    "all":   "🌐 Semua (Bot + Grup)",
}

def get_otp_search_scope() -> str:
    return settings.get("otpSearchScope", "bot")

def is_otp_search_allowed(chat_type: str) -> bool:
    scope = get_otp_search_scope()
    if scope == "all":
        return True
    if scope == "bot":
        return chat_type == "private"
    if scope == "group":
        return chat_type in ("group", "supergroup")
    return True

def otp_scope_not_allowed_text() -> str:
    scope = get_otp_search_scope()
    if scope == "bot":
        return "❌ <b>Cari OTP</b> hanya bisa dipakai lewat <b>chat pribadi bot</b>, bukan di grup."
    if scope == "group":
        return "❌ <b>Cari OTP</b> hanya bisa dipakai <b>di dalam grup</b>, bukan di chat pribadi bot."
    return "❌ <b>Cari OTP</b> sedang tidak tersedia di sini."

def cycle_otp_scope() -> str:
    scope = get_otp_search_scope()
    idx = OTP_SCOPE_ORDER.index(scope) if scope in OTP_SCOPE_ORDER else 0
    new_scope = OTP_SCOPE_ORDER[(idx + 1) % len(OTP_SCOPE_ORDER)]
    settings["otpSearchScope"] = new_scope
    save_settings()
    return new_scope

def search_otp_records(uid: str, query: str, is_admin_search: bool = False, window_minutes: int = None):
    """
    Cari OTP di otp_log berdasarkan nomor penuh atau beberapa digit terakhir,
    dibatasi dalam X menit terakhir (settings['otpSearchWindowMinutes']).
    Non-admin hanya bisa melihat OTP milik nomor yang di-assign ke dirinya sendiri.
    """
    digits = re.sub(r"\D", "", query or "")
    if len(digits) < 3:
        return [], 0

    window = window_minutes if window_minutes is not None else settings.get("otpSearchWindowMinutes", 5)
    cutoff = now_wib() - timedelta(minutes=window)

    results = []
    for log in reversed(otp_log):
        number = str(log.get("phoneNumber", ""))
        if not (number == digits or number.endswith(digits) or digits.endswith(number)):
            continue
        if not is_admin_search and str(log.get("userId")) != str(uid):
            continue
        ts_str = log.get("timestamp")
        try:
            ts = datetime.fromisoformat(ts_str)
        except Exception:
            continue
        if ts < cutoff:
            continue
        results.append(log)

    return results, window

async def run_otp_search_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: str, raw_query: str):
    """Jalankan pencarian OTP dan kirim hasilnya. Dipakai baik dari menu maupun command /otp."""
    is_admin_search = get_session(uid).get("is_admin") or is_admin(uid)
    digits = re.sub(r"\D", "", raw_query or "")
    if len(digits) < 3:
        return await update.effective_message.reply_text(
            "❌ Nomor tidak valid. Kirim minimal 3 digit terakhir atau nomor lengkap.\n\n"
            "Contoh: <code>7484</code> atau <code>+8801712345678</code>",
            parse_mode="HTML"
        )

    results, window = search_otp_records(uid, digits, is_admin_search=is_admin_search)

    reply_buttons = InlineKeyboardMarkup([
        [mkbtn("otp_search_again", "Cari Lagi", callback_data="cariotp_again", style="primary")],
    ])

    if not results:
        return await update.effective_message.reply_text(
            f"❌ <b>OTP Tidak Ditemukan</b>\n\n"
            f"Tidak ada OTP untuk <code>{html.escape(digits)}</code> dalam <b>{window} menit</b> terakhir.\n\n"
            f"<i>Cek kembali nomornya, atau tunggu OTP masuk lalu coba lagi.</i>",
            parse_mode="HTML",
            reply_markup=reply_buttons
        )

    # Pakai varian *_html supaya emoji Premium service/negara tampil sebagai
    # desain asli lewat <tg-emoji> di hasil pencarian ini juga.
    lines = [f"🔍 <b>Hasil Pencarian OTP</b> <i>(dalam {window} menit terakhir)</i>\n"]
    for log in results[:10]:
        svc     = services.get(log.get("service") or "", {"icon": "📱", "name": (log.get("service") or "Service").capitalize()})
        cc      = log.get("countryCode", "")
        code    = log.get("otpCode") or "-"
        ago     = format_time_ago(log.get("timestamp"))
        svc_icon_html = get_svc_icon_html(log.get('service') or '')
        flag_html = get_country_flag_html(cc)
        lines.append(
            f"{svc_icon_html} <b>{html.escape(str(svc['name']))}</b> — {flag_html} +{html.escape(str(log.get('phoneNumber')))}\n"
            f"🔑 OTP: <code>{html.escape(str(code))}</code>\n"
            f"🕐 {html.escape(str(ago))} yang lalu\n"
        )

    result_text = "\n".join(lines)
    try:
        await update.effective_message.reply_text(
            result_text,
            parse_mode="HTML",
            reply_markup=reply_buttons
        )
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        await update.effective_message.reply_text(
            _strip_tg_emoji_tags(result_text),
            parse_mode="HTML",
            reply_markup=reply_buttons
        )

async def handle_cari_otp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type if update.effective_chat else "private"
    if not is_otp_search_allowed(chat_type):
        return await update.effective_message.reply_text(otp_scope_not_allowed_text(), parse_mode="HTML")
    if not await ensure_verified(update, context):
        return
    if not is_feature_enabled("cariotp"):
        return await update.effective_message.reply_text(feature_disabled_text("Cari OTP"), parse_mode="HTML")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = "searching_otp"
    window = settings.get("otpSearchWindowMinutes", 5)
    await update.effective_message.reply_text(
        f"🔍 <b>Cari OTP</b>\n\n"
        f"Kirim nomor (bisa 4 digit terakhir atau nomor lengkap) untuk melihat OTP dalam <b>{window} menit</b> terakhir.\n\n"
        f"Contoh: <code>7484</code> atau <code>+8801712345678</code>\n\n"
        f"Kamu juga bisa langsung ketik <code>/otp 7484</code> kapan saja tanpa lewat menu ini.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("otp_cancel", "Batal", callback_data="cariotp_cancel", style="danger")]])
    )

async def cb_cariotp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    get_session(uid)["state"] = None
    try:
        await query.edit_message_text("✅ Dibatalkan.")
    except Exception:
        pass

async def cb_cariotp_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    get_session(uid)["state"] = "searching_otp"
    window = settings.get("otpSearchWindowMinutes", 5)
    await query.message.reply_text(
        f"🔍 Kirim nomor lagi (dalam <b>{window} menit</b> terakhir):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("otp_cancel", "Batal", callback_data="cariotp_cancel", style="danger")]])
    )

async def cmd_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type if update.effective_chat else "private"
    if not is_otp_search_allowed(chat_type):
        return await update.effective_message.reply_text(otp_scope_not_allowed_text(), parse_mode="HTML")
    if not await ensure_verified(update, context):
        return
    if not is_feature_enabled("cariotp"):
        return await update.effective_message.reply_text(feature_disabled_text("Cari OTP"), parse_mode="HTML")
    uid = str(update.effective_user.id)
    if not context.args:
        return await update.message.reply_text(
            "❌ <b>Format salah.</b>\n\nContoh: <code>/otp 7484</code> atau <code>/otp 8801712345678</code>",
            parse_mode="HTML"
        )
    query = " ".join(context.args)
    await run_otp_search_and_reply(update, context, uid, query)

# ─── HTTP OTP Server ───
HTTP_PORT = int(os.environ.get("HTTP_PORT", 8080))

async def http_otp_handler(request: aio_web.Request) -> aio_web.Response:
    global _tg_app
    try:
        data      = await request.json()
        number    = re.sub(r"\D", "", str(data.get("number", ""))).lstrip("0")
        otp_code  = str(data.get("otp", "")).strip().replace("-", "").replace(" ", "")
        service   = str(data.get("service", "other")).lower().strip()

        if not number:
            return aio_web.json_response({"ok": False, "error": "number required"}, status=400)

        # active_numbers এ match খোঁজো — leading zeros ছাড়া
        matched_number = None
        if number in active_numbers:
            matched_number = number
        else:
            # OTP bot ভিন্ন format এ পাঠাতে পারে, তাই suffix match করো
            for n in active_numbers:
                if n.endswith(number[-8:]) or number.endswith(n[-8:]):
                    matched_number = n
                    break

        if not matched_number:
            logger.warning(f"⚠️ HTTP /otp: number {number} not in active_numbers")
            return aio_web.json_response({"ok": False, "error": "number not active"}, status=404)

        an_data = active_numbers[matched_number]
        uid     = an_data["userId"]
        cc      = an_data.get("countryCode", "")

        # Sama seperti jalur grup: cuma proses kalau nomor ini masih ada di
        # daftar yang sedang ditampilkan ke user (belum diganti/expired).
        if not _number_still_assigned(uid, matched_number):
            logger.info(f"⏭️ HTTP /otp untuk +{matched_number} diabaikan — nomor sudah tidak aktif untuk user {uid}.")
            active_numbers.pop(matched_number, None)
            rebuild_suffix_index()
            await async_save_active()
            return aio_web.json_response({"ok": False, "error": "number no longer assigned to user"}, status=404)

        otp_key = f"http_{otp_code}_{matched_number}"
        if an_data.get("lastOTP") == otp_key or _is_duplicate_otp(matched_number, otp_code):
            return aio_web.json_response({"ok": True, "info": "duplicate"})
        an_data["lastOTP"]  = otp_key
        an_data["otpCount"] = an_data.get("otpCount", 0) + 1
        save_active()

        earned  = await add_earning(uid, cc)
        balance = get_user_earnings(uid)["balance"]
        svc     = services.get(service, {"icon": "📱", "name": service.capitalize()})
        country = countries.get(cc, {"flag": "🌍", "name": cc})

        asyncio.create_task(record_otp_event("http", uid, cc, service, matched_number, otp_code))

        notify = (
            f"📨 <b>OTP Received!</b>\n\n"
            f"{get_svc_icon_html(service)} <b>Service:</b> {html.escape(svc['name'])}\n"
            f"{get_country_flag_html(cc)} <b>Country:</b> {html.escape(country['name'])}\n"
            f"📞 <b>Number:</b> <code>+{html.escape(str(matched_number))}</code>\n"
        )
        if otp_code:
            notify += f"\n🔑 <b>OTP Code:</b> <code>{html.escape(str(otp_code))}</code>\n"
        notify += f"\n💵 <b>+{earned:.2f} USD earned!</b>\n💰 <b>Balance: {balance:.2f} USD</b>"

        if _tg_app:
            try:
                sent_notify = await safe_send_message(_tg_app.bot, int(uid), notify, parse_mode="HTML")
                await _track_otp_notify_msg(matched_number, sent_notify.message_id)
            except Exception as e:
                logger.error(f"HTTP OTP notify send error: {e}")

        otp_log.append({
            "phoneNumber": matched_number, "userId": uid, "countryCode": cc,
            "service": service, "otpCode": otp_code, "earned": earned,
            "messageId": None, "delivered": True,
            "source": "http_api",
            "timestamp": now_wib().isoformat()
        })
        save_otp_log()

        logger.info(f"✅ HTTP /otp processed: +{matched_number} otp={otp_code} uid={uid}")
        return aio_web.json_response({"ok": True, "earned": earned, "balance": balance})

    except Exception as e:
        logger.error(f"HTTP /otp handler error: {e}")
        return aio_web.json_response({"ok": False, "error": str(e)}, status=500)

async def start_http_server():
    http_app = aio_web.Application()
    http_app.router.add_post("/otp", http_otp_handler)
    http_app.router.add_get("/health", lambda r: aio_web.json_response({"ok": True}))
    http_app["telegram_app"] = _tg_app
    webhook_routes = {}
    for ptype in ("augestel", "ksi", "elite_sms_api"):
        for path in _webhook_paths_for_ptype(ptype):
            webhook_routes.setdefault(path, set()).add(ptype)
    for path, providers in webhook_routes.items():
        expected = next(iter(providers)) if len(providers) == 1 else None
        http_app.router.add_post(
            path,
            lambda request, expected=expected: panel_webhook_handler(request, expected),
        )
        http_app.router.add_get(
            f"{path}/health",
            lambda request, expected=expected, path=path: aio_web.json_response(
                {"ok": True, "provider": expected, "path": path}
            ),
        )
    # Account webhook URLs may use their own path. Keep the explicit routes
    # above for health checks, and let the signed handler accept custom paths
    # without requiring a bot restart when an account is added later.
    http_app.router.add_post("/{tail:.*}", panel_webhook_handler)
    runner = aio_web.AppRunner(http_app)
    await runner.setup()
    site = aio_web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    logger.info(f"🌐 HTTP OTP server started → port {HTTP_PORT}")

def generate_totp(secret: str):
    try:
        clean = secret.replace(" ", "").replace("-", "").upper()
        missing_padding = (8 - len(clean) % 8) % 8
        if missing_padding:
            clean += "=" * missing_padding
        totp = pyotp.TOTP(clean)
        token = totp.now()
        remaining = 30 - (int(time.time()) % 30)
        return {"token": token, "timeRemaining": remaining}
    except Exception as e:
        logger.error(f"generate_totp error (secret_len={len(secret)}): {e}")
        return None

# ─── Baileys API (WhatsApp) Helpers ───
_green_state  = {"authorized": False}
_green_owner  = load_json(WA_OWNER_FILE, {"uid": None})
_wa_pair_lock = None

def save_green_owner():
    save_json(WA_OWNER_FILE, _green_owner)

def baileys_request(method: str, path: str, body=None) -> dict:
    url     = f"{BAILEYS_URL}{path}"
    headers = {"Content-Type": "application/json"}
    data    = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"Baileys API error [{path}]: {e}")
        return {}

async def green_get_state(uid: str = None) -> str:
    loop   = asyncio.get_event_loop()
    path   = f"/status?userId={uid}" if uid else "/status?userId=global"
    result = await loop.run_in_executor(None, lambda: baileys_request("GET", path))
    if result.get("connected"):
        return "authorized"
    return "notAuthorized"


async def green_api_monitor(app):
    logger.info("🟢 Baileys monitor started")
    fail_counts = {}

    while True:
        await asyncio.sleep(30)
        try:
            for uid in list(wa_sessions.keys()):
                if not wa_sessions.get(uid, {}).get("connected"):
                    continue
                try:
                    state = await green_get_state(uid)
                    if state != "authorized":
                        fail_counts[uid] = fail_counts.get(uid, 0) + 1
                        logger.warning(f"⚠️ Baileys: WA check fail #{fail_counts[uid]} uid={uid}")
                        if fail_counts[uid] >= 5:
                            fail_counts.pop(uid, None)
                            wa_sessions.pop(uid, None)
                            logger.warning(f"⚠️ Baileys: WhatsApp disconnected! uid={uid}")
                            try:
                                await app.bot.send_message(
                                    int(uid),
                                    "⚠️ <b>WhatsApp Disconnected!</b>\n\n"
                                    "Your WhatsApp has been disconnected from the bot.\n"
                                    "Press the button below to reconnect.",
                                    parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup([[
                                        mkbtn("wa_connect", "Connect WhatsApp", callback_data="wa_connect", style="success")
                                    ]])
                                )
                            except Exception as e:
                                logger.error(f"Disconnect notify error uid={uid}: {e}")
                    else:
                        fail_counts.pop(uid, None)
                except Exception as e:
                    logger.error(f"Baileys monitor error uid={uid}: {e}")
        except Exception as e:
            logger.error(f"Baileys monitor loop error: {e}")

async def send_otp_to_group(otp_code: str, group_msg: str, retries: int = 5):
    """Direct HTTP দিয়ে OTP group এ পাঠাও — PTB rate limit এড়াতে"""
    import aiohttp as _aiohttp
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    OTP_GROUP_ID,
        "text":       group_msg,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": str(otp_code), "copy_text": {"text": str(otp_code)}}],
                [
                    {"text": "☎️ Numbers", "url": "https://t.me/EARNING_HUB_NUMBER_BOT"},
                    {"text": "💬 Chats",   "url": "https://t.me/nexion_otp_group"},
                ]
            ]
        }
    }
    for attempt in range(1, retries + 1):
        try:
            async with _aiohttp.ClientSession() as s:
                async with s.post(url, json=payload, timeout=15) as r:
                    if r.status == 200:
                        return True
                    elif r.status == 429:
                        data       = await r.json()
                        retry_after = data.get("parameters", {}).get("retry_after", 10)
                        logger.warning(f"⚠️ OTP Group Flood Wait {retry_after}s")
                        await asyncio.sleep(retry_after + 1)
                        continue
                    else:
                        logger.error(f"❌ OTP group send failed ({r.status})")
                        return False
        except Exception as e:
            logger.error(f"❌ OTP group send error: {e}")
            if attempt < retries:
                await asyncio.sleep(3)
    return False
    logger.info("🟢 Baileys monitor started")
    fail_counts = {}  # { uid: fail_count }

    while True:
        await asyncio.sleep(30)
        try:
            for uid in list(wa_sessions.keys()):
                if not wa_sessions.get(uid, {}).get("connected"):
                    continue
                try:
                    state = await green_get_state(uid)
                    if state != "authorized":
                        fail_counts[uid] = fail_counts.get(uid, 0) + 1
                        logger.warning(f"⚠️ Baileys: WA check fail #{fail_counts[uid]} uid={uid}")
                        # ৫ বার fail হলে disconnect বলবে
                        if fail_counts[uid] >= 5:
                            fail_counts.pop(uid, None)
                            wa_sessions.pop(uid, None)
                            logger.warning(f"⚠️ Baileys: WhatsApp disconnected! uid={uid}")
                            try:
                                await app.bot.send_message(
                                    int(uid),
                                    "⚠️ <b>WhatsApp Disconnected!</b>\n\n"
                                    "Your WhatsApp has been disconnected from the bot.\n"
                                    "Press the button below to reconnect.",
                                    parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup([[
                                        mkbtn("wa_connect", "Connect WhatsApp", callback_data="wa_connect", style="success")
                                    ]])
                                )
                            except Exception as e:
                                logger.error(f"Disconnect notify error uid={uid}: {e}")
                    else:
                        fail_counts.pop(uid, None)
                except Exception as e:
                    logger.error(f"Baileys monitor error uid={uid}: {e}")
        except Exception as e:
            logger.error(f"Baileys monitor loop error: {e}")

async def get_wa_pairing_code(phone: str, user_id: str) -> str:
    digits = re.sub(r"\D", "", phone)
    logger.info(f"📱 Baileys pairing for: +{digits} uid={user_id}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: baileys_request("POST", "/start", {"userId": user_id})
    )
    await asyncio.sleep(3)
    result = await loop.run_in_executor(
        None,
        lambda: baileys_request("POST", "/pair", {"phone": digits, "userId": user_id})
    )
    logger.info(f"Baileys pairing result: {result}")
    if result.get("connected"):
        raise Exception("WhatsApp is already connected.")
    if result.get("code"):
        code  = str(result["code"])
        clean = re.sub(r"[^A-Z0-9]", "", code.upper())
        if len(clean) >= 8:
            return f"{clean[:4]}-{clean[4:8]}"
        return code
    raise Exception(
        result.get("error") or
        "Pairing code not received. Please check if the Baileys server is running."
    )

async def monitor_wa_connection(uid: str, context):
    logger.info(f"🔍 Waiting for WA auth: {uid}")
    for _ in range(60):
        await asyncio.sleep(5)
        try:
            state = await green_get_state(uid)
            if state == "authorized":
                wa_sessions[uid] = {"connected": True}
                logger.info(f"✅ WA connected: uid={uid}")
                try:
                    await context.bot.send_message(
                        int(uid),
                        "✅ <b>WhatsApp Connected!</b>\n\n"
                        "🟢 Your WhatsApp has been successfully connected.\n"
                        "WA check will appear when numbers are assigned.\n\n"
                        "Press the button below to disconnect:",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [mkbtn("wa_disconnect", "Logout / Disconnect", callback_data="wa_disconnect", style="danger")],
                            [mkbtn("wa_status", "Check Status", callback_data="wa_status", style="primary")],
                        ])
                    )
                except:
                    pass
                break
        except Exception as e:
            logger.warning(f"monitor_wa_connection error: {e}")

async def check_wa_number(phone: str, user_id: str):
    # ── Global WA enabled হলে admin WA দিয়ে check করো ──
    effective_uid = user_id
    if global_wa_data.get("enabled") and global_wa_data.get("connected"):
        effective_uid = global_wa_data.get("uid", user_id)

    if not wa_sessions.get(effective_uid, {}).get("connected"):
        state = await green_get_state(effective_uid)
        if state != "authorized":
            return None
        wa_sessions[effective_uid] = {"connected": True}
    digits = re.sub(r"\D", "", phone)
    loop   = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: baileys_request("POST", "/check", {"numbers": [digits], "userId": effective_uid})
        )
        logger.info(f"📱 WA check +{digits}: {result}")
        results = result.get("results", {})
        val = results.get(digits)
        if val is True:  return True
        if val is False: return False
        return None
    except Exception as e:
        logger.warning(f"check_wa_number error +{digits}: {e}")
        return None

# ─── Mail.tm API ───
def mailtm_request(method: str, path: str, body=None, token=None):
    url = f"https://api.mail.tm{path}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            return err
        except:
            return None
    except Exception as e:
        logger.error(f"Mail.tm error: {e}")
        return None

async def mailtm_request_async(method: str, path: str, body=None, token=None):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: mailtm_request(method, path, body, token)
    )

def random_str(n: int, chars="abcdefghijklmnopqrstuvwxyz0123456789") -> str:
    import random
    return "".join(random.choice(chars) for _ in range(n))

async def create_fresh_email():
    try:
        domains = await mailtm_request_async("GET", "/domains?page=1")
        domain_list = domains if isinstance(domains, list) else (domains or {}).get("hydra:member", [])
        if not domain_list:
            return None
        domain = domain_list[0]["domain"]
        username = random_str(12)
        password = random_str(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
        address  = f"{username}@{domain}"
        account = None
        for _ in range(3):
            account = await mailtm_request_async("POST", "/accounts", {"address": address, "password": password})
            if account and account.get("id"):
                break
            await asyncio.sleep(3)
        if not account or not account.get("id"):
            return None
        token_res = await mailtm_request_async("POST", "/token", {"address": address, "password": password})
        if not token_res or not token_res.get("token"):
            return None
        return {
            "address":   address,
            "sidToken":  token_res["token"],
            "provider":  "mailtm",
            "createdAt": now_wib().isoformat()
        }
    except Exception as e:
        logger.error(f"createFreshEmail error: {e}")
        return None

async def get_email_inbox(email_obj: dict):
    try:
        data = await mailtm_request_async("GET", "/messages?page=1", token=email_obj.get("sidToken"))
        msgs = data if isinstance(data, list) else (data or {}).get("hydra:member", [])
        return [{"id": m.get("id"), "from": (m.get("from") or {}).get("address", ""),
                 "subject": m.get("subject", ""), "date": m.get("createdAt", "")} for m in msgs]
    except:
        return []

async def get_email_message(msg_id: str, email_obj: dict) -> str:
    try:
        data = await mailtm_request_async("GET", f"/messages/{msg_id}", token=email_obj.get("sidToken"))
        if not data:
            return ""
        text = data.get("text", "")
        html = (data.get("html") or [""])[0]
        raw = text or re.sub(r"<[^>]*>", " ", html)
        return re.sub(r"\s+", " ", raw).strip()
    except:
        return ""

# ─── Membership Check ───
async def check_membership(user_id: int, app) -> dict:
    result = {"mainChannel": False, "chatGroup": False, "otpGroup": False, "allJoined": False}
    try:
        m = await app.bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        result["mainChannel"] = m.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"Main channel check: {e}")
    try:
        m = await app.bot.get_chat_member(CHAT_GROUP_ID, user_id)
        result["chatGroup"] = m.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"Chat group check: {e}")
    try:
        m = await app.bot.get_chat_member(OTP_GROUP_ID, user_id)
        result["otpGroup"] = m.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"OTP group check: {e}")
    result["allJoined"] = result["mainChannel"] and result["chatGroup"] and result["otpGroup"]
    return result

# ─── Keyboards ───
# ─── Menu utama versi "reply keyboard" (menu bawah, berwarna, selalu nempel di atas kolom ketik) ───
# Menu inline lama sudah dihapus — ini satu-satunya menu utama sekarang.
#
# Setiap tombol menu bawah didefinisikan SATU KALI di sini: (translation_key,
# emoji_slot_key, emoji_default, action_key). emoji_slot_key mengacu ke slot
# Custom Emoji kategori "button" (lihat _BUTTON_EMOJI_DEFAULTS) — jadi kalau
# admin mengubah emoji tombol lewat menu Custom Emoji, label tombol ini
# OTOMATIS ikut berubah (emoji-nya diambil live lewat get_btn_emoji()),
# dan REPLY_MENU_LABELS (untuk mengenali tombol mana yang ditekan user) juga
# dibangun dari daftar yang SAMA supaya selalu sinkron dengan apa yang benar-
# benar ditampilkan (baik emoji maupun bahasa).
MAIN_MENU_BUTTON_SPECS = [
    ("btn_get_number",   "get_number",   "☎️", "getnumber"),
    ("btn_get_file",     "get_file",     "📄", "getfile"),
    ("btn_search_otp",   "otp",          "🔍", "cariotp"),
    ("btn_live_traffic", "live_traffic", "🔥", "livetraffic"),
    ("btn_tools",        "tools",        "🛠️", "tools"),
    ("btn_profile",      "profile",      "👤", "profil"),
    ("btn_support",      "support",      "💬", "support"),
    ("btn_minimize_menu","minimize_menu","🔽", "minimizemenu"),
]

def _menu_label_text(text: str, emoji_key: str, emoji_default: str) -> str:
    """Gabungkan teks tombol dengan emoji TERKINI (mengikuti Custom Emoji admin).

    Kalau slot ini punya custom_emoji_id, Telegram akan menampilkan ikon custom
    emoji ASLI di tombol lewat icon_custom_emoji_id (lihat _make_btn_kwargs) —
    jadi karakter emoji TIDAK boleh ditempel lagi di depan teks, supaya tidak
    tampil dobel (ikon custom emoji + karakter ✨/emoji biasa di teks). Sama
    persis dengan cara mkbtn() menghindari dobel emoji di tombol inline."""
    if get_btn_emoji_id(emoji_key, emoji_default):
        return text
    emoji_char = get_btn_emoji(emoji_key, emoji_default)
    return f"{emoji_char} {text}".strip() if emoji_char else text

def _menu_btn_label(uid: str, tr_key: str, emoji_key: str, emoji_default: str) -> str:
    """Label tombol menu bawah dengan emoji TERKINI (mengikuti Custom Emoji admin)."""
    return _menu_label_text(t(uid, tr_key), emoji_key, emoji_default)

def main_reply_keyboard(uid: str = "0"):
    labels = {spec[3]: _menu_btn_label(uid, spec[0], spec[1], spec[2]) for spec in MAIN_MENU_BUTTON_SPECS}

    # Pre-fetch custom emoji IDs for each button slot so icon shows for ALL users
    _eids = {spec[1]: get_btn_emoji_id(spec[1], spec[2]) for spec in MAIN_MENU_BUTTON_SPECS}

    row1 = []
    if is_feature_enabled("getnumber"):
        row1.append(KeyboardButton(labels["getnumber"], api_kwargs=_make_btn_kwargs("success", _eids.get("get_number"))))
    if is_feature_enabled("getfile"):
        row1.append(KeyboardButton(labels["getfile"], api_kwargs=_make_btn_kwargs("success", _eids.get("get_file"))))

    row1b = []
    if is_feature_enabled("cariotp") and is_otp_search_allowed("private"):
        row1b.append(KeyboardButton(labels["cariotp"], api_kwargs=_make_btn_kwargs("success", _eids.get("otp"))))
    if is_feature_enabled("livetraffic"):
        row1b.append(KeyboardButton(labels["livetraffic"], api_kwargs=_make_btn_kwargs("danger", _eids.get("live_traffic"))))

    row2 = []
    if is_feature_enabled("tempmail") or is_feature_enabled("twofa"):
        row2.append(KeyboardButton(labels["tools"], api_kwargs=_make_btn_kwargs("success", _eids.get("tools"))))
    # Tombol profil selalu tampil — walau balance/withdraw/referral dimatikan,
    # profil tetap berguna (statistik OTP, ganti bahasa, dll)
    row2.append(KeyboardButton(labels["profil"], api_kwargs=_make_btn_kwargs("success", _eids.get("profile"))))

    row3 = []
    if is_feature_enabled("support"):
        row3.append(KeyboardButton(labels["support"], api_kwargs=_make_btn_kwargs("danger", _eids.get("support"))))

    rows = [r for r in (row1, row1b, row2, row3) if r]
    if not rows:
        rows = [[KeyboardButton(t(uid, "all_features_off"), api_kwargs=_make_btn_kwargs("danger"))]]
    # Tombol "Minimize Menu" eksplisit sengaja TIDAK ditampilkan lagi — biar
    # baris menu lebih ringkas. Menu bawah masih bisa disembunyikan kapan
    # saja lewat ikon panah minimize bawaan Telegram (di sebelah kolom
    # ketik, aktif karena is_persistent=False) dan dimunculkan lagi lewat
    # /menu atau tombol "📲 Tampilkan Menu" (lihat handle_minimize_menu).
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=False)

async def send_bottom_menu(context: ContextTypes.DEFAULT_TYPE, chat_id, uid: str = "0"):
    """Send / refresh the main reply keyboard at the bottom of the chat."""
    try:
        await safe_send_message(
            context.bot, chat_id,
            t_html(uid, "menu_title"),
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(uid),
        )
    except Exception as e:
        logger.warning(f"send_bottom_menu error: {e}")

def verify_keyboard():
    return InlineKeyboardMarkup([
        [mkbtn("main_ch", "📢 Main Channel", url=MAIN_CHANNEL_URL, style="success", auto_icon=False)],
        [mkbtn("num_ch", "💬 Number Channel", url=CHAT_GROUP, style="success", auto_icon=False)],
        [mkbtn("otp_grp", "📨 OTP Group", url=OTP_GROUP, style="success", auto_icon=False)],
        [mkbtn("verify_btn", "VERIFY MEMBERSHIP", callback_data="verify_user", style="success")],
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [mkbtn("live_stock", "Stock Report", callback_data="admin_stock", style="success"),
         mkbtn("a_user_stats", "User Stats", callback_data="admin_users", style="success")],
        [mkbtn("a_live_traffic", "Live Traffic", callback_data="admin_live_traffic", style="danger"),
         mkbtn("a_otp_log", "OTP Log", callback_data="admin_otp_log", style="success")],
        [mkbtn("a_live_timeline", "Live Timeline", callback_data="admin_live_timeline", style="primary")],
        [mkbtn("a_dashboard", "Dashboard Statistik", callback_data="admin_dashboard", style="danger")],
        [mkbtn("a_broadcast", "Broadcast", callback_data="admin_broadcast", style="success")],
        [mkbtn("a_add_numbers", "Add Numbers", callback_data="admin_add_numbers", style="success"),
         mkbtn("a_upload", "Upload File", callback_data="admin_upload", style="success")],
        [mkbtn("a_delete", "Delete Numbers", callback_data="admin_delete", style="danger"),
         mkbtn("a_manage_svc", "Manage Services", callback_data="admin_manage_services", style="success")],
        [mkbtn("a_manage_cntry", "Manage Countries", callback_data="admin_manage_countries", style="success"),
         mkbtn("a_settings", "Settings", callback_data="admin_settings", style="success")],
        [mkbtn("a_prices", "Country Prices", callback_data="admin_country_prices", style="success"),
         mkbtn("a_withdrawals", "Withdrawals", callback_data="admin_withdrawals", style="danger")],
        [mkbtn("a_balance_mgmt", "Balance Management", callback_data="admin_balance_manage", style="success"),
         mkbtn("a_referral_st", "Referral Stats", callback_data="admin_referral_stats", style="success")],
        [mkbtn("a_otp_panels", "OTP Panels", callback_data="admin_panels", style="success"),
         mkbtn("a_global_wa", "Global WA", callback_data="admin_global_wa", style="success")],
        [mkbtn("a_custom_emoji", "Custom Emoji", callback_data="admin_custom_emoji", style="primary")],
        [mkbtn("a_logout", "Logout", callback_data="admin_logout", style="danger")],
    ])

# ─── User Session State ───
user_sessions = {}

# BUG FIX: active_numbers persist ke disk lintas restart, tapi user_sessions
# cuma di memory. Kalau tidak di-seed ulang, begitu bot restart,
# sess["current_numbers"] semua user jadi kosong padahal active_numbers masih
# ada isinya → _number_still_assigned() bakal selalu False untuk nomor yang
# sebenarnya masih sah, jadi OTP pertama yang masuk setelah restart bakal
# salah dianggap "sudah tidak aktif" dan langsung dilepas/tidak dikirim ke
# user. Supaya konsisten, rekonstruksi current_numbers dari active_numbers
# begitu bot start.
def _seed_sessions_from_active_numbers():
    grouped: dict = {}
    for number, data in active_numbers.items():
        uid = str(data.get("userId", ""))
        if not uid:
            continue
        grouped.setdefault(uid, []).append(number)
    for uid, numbers in grouped.items():
        user_sessions[uid] = {
            "verified": False, "is_admin": is_admin(uid),
            "state": None, "data": None,
            "current_numbers": numbers, "current_service": None, "current_country": None,
            "last_number_time": 0, "last_verification_check": 0,
        }

_seed_sessions_from_active_numbers()

def get_session(uid) -> dict:
    uid = str(uid)
    if uid not in user_sessions:
        user_sessions[uid] = {
            "verified": False, "is_admin": is_admin(uid),
            "state": None, "data": None,
            "current_numbers": [], "current_service": None, "current_country": None,
            "last_number_time": 0, "last_verification_check": 0,
        }
    elif is_admin(uid):
        # Pastikan owner/admin selalu punya is_admin=True di sesi
        user_sessions[uid]["is_admin"] = True
    return user_sessions[uid]

# ─── Nomor aktif vs daftar yang SEDANG ditampilkan ke user ───
# active_numbers disimpan ke disk (ACTIVE_NUMBERS_FILE) jadi bisa "nyangkut"
# lintas restart bot, sedangkan user_sessions cuma di memory (reset tiap bot
# start/restart). Supaya OTP nomor lama tidak nyasar ke user setelah dia
# minta nomor baru ATAU setelah bot restart, kita anggap sebuah nomor benar-
# benar "aktif" untuk seorang user HANYA kalau nomor itu masih ada di
# sess["current_numbers"] — yaitu daftar nomor yang sedang tampil di layar
# Get Number user tersebut saat ini.
def _number_still_assigned(uid: str, number: str) -> bool:
    sess = get_session(uid)
    return number in (sess.get("current_numbers") or [])

async def release_numbers_for_user(context: ContextTypes.DEFAULT_TYPE, uid: str, numbers: list):
    """Lepas nomor lama dari active_numbers untuk user ini, DAN hapus juga
    pesan OTP yang sudah pernah dikirim ke chat user untuk nomor-nomor itu
    (kalau ada) — supaya begitu user klik "Get New Number"/ganti nomor, OTP
    nomor lama langsung hilang juga dari chat bot, bukan cuma berhenti
    mengirim OTP yang baru."""
    if not numbers:
        return
    changed = False
    for old in list(numbers):
        data = active_numbers.pop(old, None)
        if data:
            changed = True
            for mid in (data.get("notifyMsgIds") or []):
                try:
                    await context.bot.delete_message(int(uid), mid)
                except Exception:
                    pass
    if changed:
        rebuild_suffix_index()
        await async_save_active()

async def _track_otp_notify_msg(number: str, msg_id: int):
    """Catat message_id dari pesan OTP yang baru dikirim ke user, supaya bisa
    dihapus lagi nanti kalau user minta nomor baru (lihat release_numbers_for_user)."""
    data = active_numbers.get(number)
    if data is None:
        return
    ids = data.get("notifyMsgIds") or []
    ids.append(msg_id)
    data["notifyMsgIds"] = ids
    await async_save_active()

# ─── Verification Middleware ───
async def ensure_verified(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    uid  = str(user.id)
    sess = get_session(uid)

    # Admin সবসময় pass
    if sess["is_admin"] or is_admin(uid):
        sess["is_admin"] = True
        return True

    # Verification বন্ধ থাকলে pass
    if not settings.get("requireVerification", True):
        return True

    # Local flag চেক — chat_member handler real-time এ update করে
    if sess.get("verified") or users.get(uid, {}).get("verified", False):
        return True

    # Not verified — ask to join groups
    uid2 = str(update.effective_user.id) if update.effective_user else "0"
    msg = t_html(uid2, "verify_prompt")
    if update.callback_query:
        await update.callback_query.answer(t(uid2, "verify_alert"), show_alert=True)
        try:
            await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=verify_keyboard())
        except:
            await update.effective_message.reply_text(msg, parse_mode="HTML", reply_markup=verify_keyboard())
    else:
        await update.effective_message.reply_text(msg, parse_mode="HTML", reply_markup=verify_keyboard())
    return False

# ─── /start ───
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        uid  = str(user.id)

        if uid not in users:
            users[uid] = {
                "id": uid, "username": user.username or "no_username",
                "first_name": user.first_name or "User",
                "last_name": user.last_name or "",
                "joined": now_wib().isoformat(),
                "last_active": now_wib().isoformat(),
                "verified": False,
                "referredBy": None,
                "referralCount": 0,
            }

        if context.args and context.args[0].startswith("ref_"):
            referrer_id = context.args[0][4:]
            # শুধু referredBy সেট করো — verify সফল হওয়ার আগে count হবে না
            if (referrer_id != uid
                    and not users[uid].get("referredBy")
                    and referrer_id in users):
                users[uid]["referredBy"] = referrer_id
                users[uid]["referralVerified"] = False
                logger.info(f"🔗 Referral pending verify: uid={uid} referred by uid={referrer_id}")

        await async_save_users()

        sess = get_session(uid)
        sess["state"] = None
        sess["data"]  = None

        welcome = t(uid, "welcome")

        if sess.get("verified") or (uid in users and users[uid].get("verified")):
            await update.message.reply_text(
                t_html(uid, "welcome") + "\n\n" + t_html(uid, "choose_option"),
                parse_mode="HTML"
            )
            await send_bottom_menu(context, update.effective_chat.id, uid)
        else:
            await update.message.reply_text(
                t_html(uid, "welcome") + "\n\n" + t_html(uid, "join_groups_msg"),
                parse_mode="HTML", reply_markup=verify_keyboard()
            )
    except Exception as e:
        logger.error(f"cmd_start error: {e}")
        try:
            await update.message.reply_text("⚠️ Error occurred. Please try again.")
        except:
            pass

# ─── Verify ───
async def cb_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Checking...")

    user = update.effective_user
    uid  = str(user.id)
    membership = await check_membership(user.id, context.application)

    if membership["allJoined"]:
        sess = get_session(uid)
        sess["verified"] = True
        sess["last_verification_check"] = time.time()
        if is_admin(uid):
            sess["is_admin"] = True
        if uid in users:
            users[uid]["verified"] = True

            # ── Referral: শুধু প্রথমবার verify হলে count করো ──
            if not users[uid].get("referralVerified", False):
                referrer_id = users[uid].get("referredBy")
                if referrer_id and referrer_id in users:
                    users[uid]["referralVerified"] = True
                    users[referrer_id]["referralCount"] = users[referrer_id].get("referralCount", 0) + 1
                    referrals.setdefault(referrer_id, [])
                    if uid not in referrals[referrer_id]:
                        referrals[referrer_id].append(uid)
                    await async_save_referrals()
                    logger.info(f"✅ Referral confirmed: uid={uid} → referrer={referrer_id}")
                    try:
                        await context.bot.send_message(
                            int(referrer_id),
                            f"🎉 <b>New Referral Confirmed!</b>\n\n"
                            f"👤 <b>{html.escape(user.first_name or 'User')}</b> has joined all groups and is now verified!\n"
                            f"💸 You will earn <b>{settings.get('referralCommission', 10)}%</b> commission from their OTP income.",
                            parse_mode="HTML"
                        )
                    except:
                        pass

            await async_save_users()

        await query.edit_message_text(t_html(uid, "verify_success"), parse_mode="HTML")
        await context.bot.send_message(
            user.id, t_html(uid, "welcome_back"), parse_mode="HTML"
        )
        await send_bottom_menu(context, user.id, uid)
    else:
        msg = "❌ <b>VERIFICATION FAILED</b>\n\n"
        if not membership["mainChannel"]: msg += "❌ 1️⃣ Main Channel\n"
        if not membership["chatGroup"]:   msg += "❌ 2️⃣ Number Channel\n"
        if not membership["otpGroup"]:    msg += "❌ 3️⃣ OTP Group\n"
        msg += "\nPlease join ALL groups and click VERIFY again."
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=verify_keyboard())

# ─── Admin Panel ───
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    sess = get_session(uid)
    if not sess["is_admin"] and not is_admin(uid):
        return await update.message.reply_text("❌ Kamu tidak memiliki akses admin.")
    sess["state"] = None
    sess["data"]  = None
    await update.message.reply_text("🛠 <b>Admin Dashboard</b>\n\nSelect an option:", parse_mode="HTML", reply_markup=admin_keyboard())

# ─── GET NUMBERS ───
async def handle_get_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context):
        return
    if not is_feature_enabled("getnumber"):
        return await update.effective_message.reply_text(feature_disabled_text("Get Number"), parse_mode="HTML")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None

    # Buka menu Get Number dari awal = daftar nomor sebelumnya (kalau ada)
    # sudah tidak tampil lagi ke user → lepas juga dari active_numbers.
    if sess["current_numbers"]:
        await release_numbers_for_user(context, uid, sess["current_numbers"])
        sess["current_numbers"] = []

    avail = []
    for svc_id, svc in services.items():
        ccs = get_available_countries_for_service(svc_id)
        if ccs:
            total = sum(len(numbers_by_cs.get(cc, {}).get(svc_id, [])) for cc in ccs)
            avail.append((svc_id, svc, total))

    if not avail:
        return await update.effective_message.reply_text("📭 <b>No Numbers Available</b>\n\nPlease try again later.", parse_mode="HTML")

    # ── 3-color cycle for service buttons ──
    _svc_colors = ["success", "primary", "success", "danger"]
    buttons = []
    for i in range(0, len(avail), 2):
        row = []
        sid0, svc0 = avail[i][0], avail[i][1]
        _eid0 = get_svc_icon_id(sid0)
        # Kalau slot ini punya custom_emoji_id, ikonnya sudah tampil lewat
        # icon_custom_emoji_id — char TIDAK ditulis lagi di teks (hindari dobel).
        _lbl0 = f"{_icon_txt(get_svc_icon(sid0), _eid0)} {svc0['name']}".strip()
        row.append(InlineKeyboardButton(
            _lbl0,
            callback_data=f"svc:{sid0}",
            api_kwargs=_make_btn_kwargs(_svc_colors[i % 4], _eid0)
        ))
        if i+1 < len(avail):
            sid1, svc1 = avail[i+1][0], avail[i+1][1]
            _eid1 = get_svc_icon_id(sid1)
            _lbl1 = f"{_icon_txt(get_svc_icon(sid1), _eid1)} {svc1['name']}".strip()
            row.append(InlineKeyboardButton(
                _lbl1,
                callback_data=f"svc:{sid1}",
                api_kwargs=_make_btn_kwargs(_svc_colors[(i+1) % 4], _eid1)
            ))
        buttons.append(row)

    await update.effective_message.reply_text(
        "📋 <b>Pilih Service</b>\n\n<i>Angka dalam kurung ( ) menunjukkan stok nomor tersedia.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ─── cb_select_service — 3-COLOR FIX ───
async def cb_select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    # Pindah pilih service lagi = daftar nomor sebelumnya sudah tidak tampil
    # ke user → lepas dari active_numbers juga.
    if sess["current_numbers"]:
        await release_numbers_for_user(context, uid, sess["current_numbers"])
        sess["current_numbers"] = []
    svc_id = query.data.split(":", 1)[1]
    svc    = services.get(svc_id, {"name": svc_id, "icon": "📞"})
    ccs    = sorted(get_available_countries_for_service(svc_id), key=lambda cc: get_otp_price(cc))

    if not ccs:
        return await query.answer("❌ No numbers available", show_alert=True)

    show_count = settings.get("showCountOnCountryBtn", True)
    back_eid = get_btn_emoji_id("back", "🔙")
    buttons = []
    for i in range(0, len(ccs), 2):
        row = []
        cc1 = ccs[i]; c1 = countries[cc1]
        cnt1 = len(numbers_by_cs.get(cc1, {}).get(svc_id, []))
        flag1 = get_country_flag(cc1); flag1_id = get_country_flag_id(cc1)
        # Kalau flag1_id ada, ikonnya sudah tampil lewat icon_custom_emoji_id —
        # char TIDAK ditulis lagi di teks (hindari bendera dobel).
        _f1 = _icon_txt(flag1, flag1_id)
        label1 = f"{_f1} {c1['name']} ({cnt1})".strip() if show_count else f"{_f1} {c1['name']}".strip()
        row.append(InlineKeyboardButton(
            label1,
            callback_data=f"cc:{svc_id}:{cc1}",
            api_kwargs=_make_btn_kwargs("success", flag1_id)
        ))
        if i+1 < len(ccs):
            cc2 = ccs[i+1]; c2 = countries[cc2]
            cnt2 = len(numbers_by_cs.get(cc2, {}).get(svc_id, []))
            flag2 = get_country_flag(cc2); flag2_id = get_country_flag_id(cc2)
            _f2 = _icon_txt(flag2, flag2_id)
            label2 = f"{_f2} {c2['name']} ({cnt2})".strip() if show_count else f"{_f2} {c2['name']}".strip()
            row.append(InlineKeyboardButton(
                label2,
                callback_data=f"cc:{svc_id}:{cc2}",
                api_kwargs=_make_btn_kwargs("success", flag2_id)
            ))
        buttons.append(row)
    back_label = f"{_icon_txt(get_btn_emoji('back', '🔙'), back_eid)} Back".strip()
    buttons.append([InlineKeyboardButton(back_label, callback_data="back_services", api_kwargs=_make_btn_kwargs("danger", back_eid))])

    await query.edit_message_text(
        f"{get_svc_icon_html(svc_id)} <b>{html.escape(svc['name'])}</b> — Select Country\n\n" +
        ("" if show_count else ""),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cb_select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    _, svc_id, cc = query.data.split(":")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    count = settings.get("defaultNumberCount", 10)
    now   = time.time()

    cooldown = settings.get("cooldownSeconds", 5)
    if (now - sess["last_number_time"]) < cooldown and sess["current_numbers"]:
        remaining = int(cooldown - (now - sess["last_number_time"]))
        return await query.answer(t(uid, "cooldown_wait", sec=remaining), show_alert=True)

    # Lepas nomor lama SEBELUM ambil nomor baru agar tidak conflict di pool
    # (sekaligus hapus pesan OTP lama yang sudah terkirim ke chat user ini)
    await release_numbers_for_user(context, uid, sess["current_numbers"])

    nums = await get_multiple_numbers(cc, svc_id, uid, count)
    if not nums:
        return await query.answer("❌ Not enough numbers available.", show_alert=True)

    sess["current_numbers"] = nums
    sess["current_service"] = svc_id
    sess["current_country"] = cc
    sess["last_number_time"] = now

    country = countries.get(cc, {"flag": "🌍", "name": cc})
    svc     = services.get(svc_id, {"icon": "📞", "name": svc_id})
    price   = get_otp_price(cc)
    wa_connected = wa_sessions.get(uid, {}).get("connected", False) or (global_wa_data.get("enabled") and global_wa_data.get("connected"))

    def make_msg():
        return (
            f"✅ <b>{len(nums)} Number(s) Assigned!</b>\n\n"
            f"{get_svc_icon_html(svc_id)} <b>Service:</b> {html.escape(svc['name'])}\n"
            f"{get_country_flag_html(cc)} <b>Country:</b> {html.escape(country['name'])}\n"
            f"💵 <b>Earnings per OTP:</b> {price:.2f} USD\n\n"
            f"📌 OTP will be delivered automatically."
        )

    # ── Copy buttons — ২টা করে এক row ──
    from telegram import CopyTextButton

    def make_copy_buttons(wa_result=None):
        rows = []
        for n in nums:
            if wa_result:
                icon = "📱" if wa_result.get(n) is True else ("❌" if wa_result.get(n) is False else "⬜")
            else:
                icon = "⏳" if wa_connected else "📋"
            rows.append([InlineKeyboardButton(
                  text=f"{icon} +{n}",
                  copy_text=CopyTextButton(text=f"+{n}"), api_kwargs=_make_btn_kwargs("success"))])
        return rows

    all_numbers_text = "\n".join(f"+{n}" for n in nums)
    bottom_buttons = [
        [mkbtn("copy_all", "Copy All Numbers", copy_text=CopyTextButton(text=all_numbers_text), style="primary")],
        [mkbtn("open_otp_group", "Open OTP Group", url=OTP_GROUP, style="primary")],
        [mkbtn("get_new_numbers", "Get New Numbers", callback_data=f"newnum:{svc_id}:{cc}", style="success")],
        [mkbtn("service_list", "Service List", callback_data="back_services", style="danger")],
    ]

    buttons = make_copy_buttons() + bottom_buttons
    await query.edit_message_text(make_msg(), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

    if wa_connected:
        chat_id = query.message.chat_id
        msg_id  = query.message.message_id
        async def do_wa_check():
            results = await asyncio.gather(
                *[check_wa_number(n, uid) for n in nums],
                return_exceptions=True
            )
            res = {n: (r if not isinstance(r, Exception) else None)
                   for n, r in zip(nums, results)}
            try:
                await context.bot.edit_message_text(
                    make_msg(), chat_id=chat_id, message_id=msg_id,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(make_copy_buttons(res) + bottom_buttons)
                )
            except: pass
        asyncio.create_task(do_wa_check())
        asyncio.create_task(do_wa_check())

async def cb_new_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    _, svc_id, cc = query.data.split(":")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    now  = time.time()
    cooldown = settings.get("cooldownSeconds", 5)

    if (now - sess["last_number_time"]) < cooldown:
        remaining = int(cooldown - (now - sess["last_number_time"]))
        return await query.answer(t(uid, "cooldown_wait", sec=remaining), show_alert=True)

    count = settings.get("defaultNumberCount", 10)

    # Lepas nomor lama SEBELUM ambil nomor baru agar tidak conflict di pool
    # (sekaligus hapus pesan OTP lama yang sudah terkirim ke chat user ini)
    await release_numbers_for_user(context, uid, sess["current_numbers"])

    nums  = await get_multiple_numbers(cc, svc_id, uid, count)
    if not nums:
        return await query.answer("❌ No numbers available.", show_alert=True)

    sess["current_numbers"] = nums
    sess["last_number_time"] = now

    country = countries.get(cc, {"flag": "🌍", "name": cc})
    svc     = services.get(svc_id, {"icon": "📞", "name": svc_id})
    price   = get_otp_price(cc)
    wa_connected = wa_sessions.get(uid, {}).get("connected", False) or (global_wa_data.get("enabled") and global_wa_data.get("connected"))

    def make_msg_new():
        return (
            f"🔄 <b>{len(nums)} New Number(s)!</b>\n\n"
            f"{get_svc_icon_html(svc_id)} <b>Service:</b> {html.escape(svc['name'])}\n"
            f"{get_country_flag_html(cc)} <b>Country:</b> {html.escape(country['name'])}\n"
            f"💵 <b>Earnings per OTP:</b> {price:.2f} USD\n\n"
            f"📌 OTP will be delivered automatically."
        )

    from telegram import CopyTextButton

    def make_copy_buttons_new(wa_result=None):
        rows = []
        for n in nums:
            if wa_result:
                icon = "📱" if wa_result.get(n) is True else ("❌" if wa_result.get(n) is False else "⬜")
            else:
                icon = "⏳" if wa_connected else "📋"
            rows.append([InlineKeyboardButton(
                  text=f"{icon} +{n}",
                  copy_text=CopyTextButton(text=f"+{n}"), api_kwargs=_make_btn_kwargs("success"))])
        return rows

    all_numbers_text_new = "\n".join(f"+{n}" for n in nums)
    bottom_buttons_new = [
        [mkbtn("copy_all", "Copy All Numbers", copy_text=CopyTextButton(text=all_numbers_text_new), style="primary")],
        [mkbtn("open_otp_group", "Open OTP Group", url=OTP_GROUP, style="primary")],
        [mkbtn("get_new_numbers", "Get New Numbers", callback_data=f"newnum:{svc_id}:{cc}", style="success")],
        [mkbtn("service_list", "Service List", callback_data="back_services", style="danger")],
    ]

    buttons = make_copy_buttons_new() + bottom_buttons_new
    await query.edit_message_text(make_msg_new(), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

    if wa_connected:
        chat_id = query.message.chat_id
        msg_id  = query.message.message_id
        async def do_wa_check_new():
            results = await asyncio.gather(
                *[check_wa_number(n, uid) for n in nums],
                return_exceptions=True
            )
            res = {n: (r if not isinstance(r, Exception) else None)
                   for n, r in zip(nums, results)}
            try:
                await context.bot.edit_message_text(
                    make_msg_new(), chat_id=chat_id, message_id=msg_id,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(make_copy_buttons_new(res) + bottom_buttons_new)
                )
            except: pass
        asyncio.create_task(do_wa_check_new())

async def cb_back_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    # Klik "Back"/kembali ke daftar service = daftar nomor sebelumnya sudah
    # tidak tampil lagi ke user → lepas juga dari active_numbers, supaya OTP
    # untuk nomor itu berikutnya cuma numpang lewat di grup, tidak dikirim ke user.
    if sess["current_numbers"]:
        await release_numbers_for_user(context, uid, sess["current_numbers"])
        sess["current_numbers"] = []
    avail = []
    for svc_id, svc in services.items():
        ccs = get_available_countries_for_service(svc_id)
        if ccs:
            total = sum(len(numbers_by_cs.get(cc, {}).get(svc_id, [])) for cc in ccs)
            avail.append((svc_id, svc, total))

    # ── 3-color cycle ──
    _svc_colors = ["success", "primary", "success", "danger"]
    buttons = []
    for i in range(0, len(avail), 2):
        row = []
        sid0, svc0 = avail[i][0], avail[i][1]
        _eid0 = get_svc_icon_id(sid0)
        _lbl0 = f"{_icon_txt(get_svc_icon(sid0), _eid0)} {svc0['name']}".strip()
        row.append(InlineKeyboardButton(
            _lbl0,
            callback_data=f"svc:{sid0}",
            api_kwargs=_make_btn_kwargs(_svc_colors[i % 4], _eid0)
        ))
        if i+1 < len(avail):
            sid1, svc1 = avail[i+1][0], avail[i+1][1]
            _eid1 = get_svc_icon_id(sid1)
            _lbl1 = f"{_icon_txt(get_svc_icon(sid1), _eid1)} {svc1['name']}".strip()
            row.append(InlineKeyboardButton(
                _lbl1,
                callback_data=f"svc:{sid1}",
                api_kwargs=_make_btn_kwargs(_svc_colors[(i+1) % 4], _eid1)
            ))
        buttons.append(row)

    await query.edit_message_text(
        "📋 <b>Pilih Service</b>\n\n<i>Angka dalam kurung ( ) menunjukkan stok nomor tersedia.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ═══════════════════════════════════════════════════════
# ─── GET FILE — Download SEMUA nomor suatu negara ───
# ═══════════════════════════════════════════════════════
def build_number_file(nums: list, svc: dict, country: dict, uid: str) -> tuple:
    """Bangun konten file .txt elegan berisi SEMUA nomor dari DB, return (content, filename)."""
    now   = now_wib()
    total = len(nums)
    W     = 25  # lebar garis (mobile-friendly)

    def line(char="─"): return char * W
    def line2(char="═"): return char * W

    header = [
        line2(),
        "  ◆ NEXION NUMBER BOT",
        "  Number Database Export",
        line2(),
        "",
        f"  ▸ Service  : {svc.get('icon','📞')} {svc.get('name','-')}",
        f"  ▸ Country  : {country.get('flag','🌍')} {country.get('name','-')}",
        f"  ▸ Total    : {total:,} numbers",
        f"  ▸ Date     : {now.strftime('%d/%m/%Y %H:%M')}",
        f"  ▸ By User  : ID {uid}",
        "",
        line(),
        "   #    Phone Number",
        line(),
        "",
    ]

    body = []
    for i, n in enumerate(nums, 1):
        body.append(f"  {i:>4}.  +{n}")
        if i % 50 == 0 and i < total:
            body.append(f"  {line()}  [{i}/{total}]")

    footer = [
        "",
        line2(),
        f"  ✔ Total  : {total:,} numbers",
        f"  ✔ Source : NEXION Bot",
        line2(),
    ]

    content  = "\n".join(header + body + footer)
    safe_svc = re.sub(r"[^a-zA-Z0-9]+", "_", svc.get("name", "service")).strip("_").lower() or "service"
    safe_cc  = re.sub(r"[^a-zA-Z0-9]+", "_", str(country.get("name", "cc"))).strip("_").lower() or "cc"
    filename = f"NEXION_{safe_svc}_{safe_cc}_{total}nums_{now.strftime('%Y%m%d_%H%M%S')}.txt"
    return content, filename

async def send_number_file(context: ContextTypes.DEFAULT_TYPE, chat_id: int, nums: list,
                            svc: dict, country: dict, uid: str, extra_buttons: list,
                            svc_id: str = "", cc: str = ""):
    content, filename = build_number_file(nums, svc, country, uid)
    file_obj = io.BytesIO(content.encode("utf-8"))
    file_obj.name = filename
    total = len(nums)
    caption = (
        f"📂 <b>File Nomor Siap Diunduh!</b>\n\n"
        f"┌─────────────────────────\n"
        f"│ {get_svc_icon_html(svc_id)} <b>Service :</b> {html.escape(str(svc.get('name','-')))}\n"
        f"│ {get_country_flag_html(cc)} <b>Negara  :</b> {html.escape(str(country.get('name','-')))}\n"
        f"│ 🔢 <b>Total   :</b> <code>{total:,}</code> nomor\n"
        f"│ 📅 <b>Waktu   :</b> {now_wib().strftime('%d/%m/%Y %H:%M')}\n"
        f"└─────────────────────────\n\n"
        f"📌 OTP akan otomatis muncul di Grup OTP."
    )
    kb = InlineKeyboardMarkup(extra_buttons)
    try:
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(file_obj, filename=filename),
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        logger.warning(f"⚠️ Kirim file dgn custom emoji premium gagal ({e}) — coba ulang pakai emoji biasa.")
        file_obj.seek(0)
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(file_obj, filename=filename),
            caption=_strip_tg_emoji_tags(caption),
            parse_mode="HTML",
            reply_markup=_strip_btn_icon_kwargs(kb)
        )

def file_flow_buttons(svc_id: str, cc: str) -> list:
    return [
        [mkbtn("open_otp_group", "Open OTP Group", url=OTP_GROUP, style="primary")],
        [mkbtn("file_redownload", "Download Ulang", callback_data=f"filenew:{svc_id}:{cc}", style="success")],
        [mkbtn("file_pick_cntry", "Pilih Negara Lain", callback_data=f"filesvc:{svc_id}", style="primary")],
        [mkbtn("file_svc_list", "Pilih Service", callback_data="fileback_services", style="danger")],
    ]

async def handle_get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context):
        return
    if not is_feature_enabled("getfile"):
        return await update.effective_message.reply_text(feature_disabled_text("Get File"), parse_mode="HTML")
    sess = get_session(str(update.effective_user.id))
    sess["state"] = None

    avail = []
    for svc_id, svc in services.items():
        ccs = get_available_countries_for_service(svc_id)
        if ccs:
            total = sum(len(numbers_by_cs.get(cc, {}).get(svc_id, [])) for cc in ccs)
            avail.append((svc_id, svc, total))

    if not avail:
        return await update.effective_message.reply_text("📭 <b>No Numbers Available</b>\n\nPlease try again later.", parse_mode="HTML")

    _svc_colors = ["success", "primary", "success", "danger"]
    buttons = []
    for i in range(0, len(avail), 2):
        row = []
        sid0, svc0 = avail[i][0], avail[i][1]
        _eid0 = get_svc_icon_id(sid0)
        _lbl0 = f"{_icon_txt(get_svc_icon(sid0), _eid0)} {svc0['name']}".strip()
        row.append(InlineKeyboardButton(
            _lbl0,
            callback_data=f"filesvc:{sid0}",
            api_kwargs=_make_btn_kwargs(_svc_colors[i % 4], _eid0)
        ))
        if i+1 < len(avail):
            sid1, svc1 = avail[i+1][0], avail[i+1][1]
            _eid1 = get_svc_icon_id(sid1)
            _lbl1 = f"{_icon_txt(get_svc_icon(sid1), _eid1)} {svc1['name']}".strip()
            row.append(InlineKeyboardButton(
                _lbl1,
                callback_data=f"filesvc:{sid1}",
                api_kwargs=_make_btn_kwargs(_svc_colors[(i+1) % 4], _eid1)
            ))
        buttons.append(row)

    await update.effective_message.reply_text(
        "📄 <b>Get File — Pilih Service</b>\n\n"
        "<i>(pilih service → pilih negara → file .txt otomatis terkirim)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def _file_flow_render(query, text: str, reply_markup: InlineKeyboardMarkup):
    """Render 1 langkah alur Get File (list Service / list Negara).

    Tombol "Pilih Negara Lain" & "Pilih Service" JUGA menempel di caption
    file .txt yang dikirim lewat send_document (bukan pesan teks biasa) —
    Telegram menolak edit_message_text pada pesan dokumen ("There is no
    text in the message to edit"), jadi tombolnya kelihatan diam/tidak
    berfungsi. Di sini: coba edit dulu (utk pesan teks biasa), kalau gagal
    (mis. karena originnya pesan dokumen) kirim pesan baru sebagai gantinya."""
    msg = query.message
    if msg is not None and getattr(msg, "text", None):
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
            return
        except Exception:
            pass
    if msg is not None:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def cb_select_service_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer()
    svc_id = query.data.split(":", 1)[1]
    svc    = services.get(svc_id, {"name": svc_id, "icon": "📞"})
    ccs    = sorted(get_available_countries_for_service(svc_id), key=lambda cc: get_otp_price(cc))

    if not ccs:
        return await query.answer("❌ No numbers available", show_alert=True)

    show_count = settings.get("showCountOnCountryBtn", True)
    back_eid = get_btn_emoji_id("back", "🔙")
    buttons = []
    for i in range(0, len(ccs), 2):
        row = []
        cc1 = ccs[i]; c1 = countries[cc1]
        cnt1 = len(numbers_by_cs.get(cc1, {}).get(svc_id, []))
        flag1 = get_country_flag(cc1); flag1_id = get_country_flag_id(cc1)
        # Kalau flag1_id ada, ikonnya sudah tampil lewat icon_custom_emoji_id —
        # char TIDAK ditulis lagi di teks (hindari bendera dobel).
        _f1 = _icon_txt(flag1, flag1_id)
        label1 = f"{_f1} {c1['name']} ({cnt1})".strip() if show_count else f"{_f1} {c1['name']}".strip()
        row.append(InlineKeyboardButton(
            label1,
            callback_data=f"filecc:{svc_id}:{cc1}",
            api_kwargs=_make_btn_kwargs("success", flag1_id)
        ))
        if i+1 < len(ccs):
            cc2 = ccs[i+1]; c2 = countries[cc2]
            cnt2 = len(numbers_by_cs.get(cc2, {}).get(svc_id, []))
            flag2 = get_country_flag(cc2); flag2_id = get_country_flag_id(cc2)
            _f2 = _icon_txt(flag2, flag2_id)
            label2 = f"{_f2} {c2['name']} ({cnt2})".strip() if show_count else f"{_f2} {c2['name']}".strip()
            row.append(InlineKeyboardButton(
                label2,
                callback_data=f"filecc:{svc_id}:{cc2}",
                api_kwargs=_make_btn_kwargs("success", flag2_id)
            ))
        buttons.append(row)
    back_label = f"{_icon_txt(get_btn_emoji('back', '🔙'), back_eid)} Back".strip()
    buttons.append([InlineKeyboardButton(back_label, callback_data="fileback_services", api_kwargs=_make_btn_kwargs("danger", back_eid))])

    await _file_flow_render(
        query,
        f"📄 {get_svc_icon_html(svc_id)} <b>{html.escape(svc['name'])}</b> — Select Country\n\n" +
        ("" if show_count else ""),
        InlineKeyboardMarkup(buttons)
    )

async def cb_select_country_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer("⏳ Menyiapkan file...")
    _, svc_id, cc = query.data.split(":")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    now  = time.time()

    cooldown = settings.get("cooldownSeconds", 5)
    if (now - sess.get("last_file_time", 0)) < cooldown:
        remaining = int(cooldown - (now - sess.get("last_file_time", 0)))
        return await query.answer(f"⏳ Tunggu {remaining} detik lagi.", show_alert=True)

    # Ambil SEMUA nomor dari database untuk negara & service ini
    nums = list(numbers_by_cs.get(cc, {}).get(svc_id, []))
    if not nums:
        return await query.answer("❌ Tidak ada nomor tersedia untuk negara ini.", show_alert=True)

    sess["last_file_time"] = now
    country = countries.get(cc, {"flag": "🌍", "name": cc, "code": cc})
    svc     = services.get(svc_id, {"icon": "📞", "name": svc_id})

    try:
        await query.edit_message_text(
            f"⏳ <b>Memproses file...</b>\n\n"
            f"{get_svc_icon_html(svc_id)} <b>{html.escape(str(svc.get('name','-')))}</b> — {get_country_flag_html(cc)} <b>{html.escape(str(country.get('name','-')))}</b>\n"
            f"🔢 Mengemas <code>{len(nums):,}</code> nomor, mohon tunggu...",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await send_number_file(
        context, query.message.chat_id, nums, svc, country, uid,
        file_flow_buttons(svc_id, cc), svc_id=svc_id, cc=cc
    )

async def cb_new_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await ensure_verified(update, context):
        return
    await query.answer("⏳ Menyiapkan ulang...")
    _, svc_id, cc = query.data.split(":")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    now  = time.time()

    cooldown = settings.get("cooldownSeconds", 5)
    if (now - sess.get("last_file_time", 0)) < cooldown:
        remaining = int(cooldown - (now - sess.get("last_file_time", 0)))
        return await query.answer(f"⏳ Tunggu {remaining} detik lagi.", show_alert=True)

    # Ambil SEMUA nomor dari database untuk negara & service ini
    nums = list(numbers_by_cs.get(cc, {}).get(svc_id, []))
    if not nums:
        return await query.answer("❌ Tidak ada nomor tersedia.", show_alert=True)

    sess["last_file_time"] = now
    country = countries.get(cc, {"flag": "🌍", "name": cc, "code": cc})
    svc     = services.get(svc_id, {"icon": "📱", "name": svc_id})

    await send_number_file(
        context, query.message.chat_id, nums, svc, country, uid,
        file_flow_buttons(svc_id, cc), svc_id=svc_id, cc=cc
    )

async def cb_back_services_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    avail = []
    for svc_id, svc in services.items():
        ccs = get_available_countries_for_service(svc_id)
        if ccs:
            total = sum(len(numbers_by_cs.get(cc, {}).get(svc_id, [])) for cc in ccs)
            avail.append((svc_id, svc, total))

    _svc_colors = ["success", "primary", "success", "danger"]
    buttons = []
    for i in range(0, len(avail), 2):
        row = []
        sid0, svc0 = avail[i][0], avail[i][1]
        _eid0 = get_svc_icon_id(sid0)
        _lbl0 = f"{_icon_txt(get_svc_icon(sid0), _eid0)} {svc0['name']}".strip()
        row.append(InlineKeyboardButton(
            _lbl0,
            callback_data=f"filesvc:{sid0}",
            api_kwargs=_make_btn_kwargs(_svc_colors[i % 4], _eid0)
        ))
        if i+1 < len(avail):
            sid1, svc1 = avail[i+1][0], avail[i+1][1]
            _eid1 = get_svc_icon_id(sid1)
            _lbl1 = f"{_icon_txt(get_svc_icon(sid1), _eid1)} {svc1['name']}".strip()
            row.append(InlineKeyboardButton(
                _lbl1,
                callback_data=f"filesvc:{sid1}",
                api_kwargs=_make_btn_kwargs(_svc_colors[(i+1) % 4], _eid1)
            ))
        buttons.append(row)

    await _file_flow_render(
        query,
        "📄 <b>Get File — Pilih Service</b>\n\n"
        "<i>(pilih service → pilih negara → file .txt otomatis terkirim)</i>",
        InlineKeyboardMarkup(buttons)
    )

# ─── PROFIL (menu gabungan: detail profil + Balance + Withdraw + Referral) ───
async def handle_profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    user = update.effective_user
    uid  = str(user.id)
    e    = get_user_earnings(uid)

    today_str = now_wib().strftime("%Y-%m-%d")
    otp_today   = sum(1 for log in otp_log
                       if str(log.get("userId")) == uid and str(log.get("timestamp", "")).startswith(today_str))
    otp_alltime = e.get("otpCount", 0)

    full_name = user.full_name or user.first_name or "User"
    username  = f"@{user.username}" if user.username else "-"

    msg = (
        f"{t_html(uid, 'profile_title')}\n\n"
        f"{t_html(uid, 'user_id')} <code>{html.escape(uid)}</code>\n"
        f"{t_html(uid, 'telegram_name')} {html.escape(full_name)}\n"
        f"{t_html(uid, 'username')} {html.escape(username)}\n\n"
        f"{t_html(uid, 'total_balance')} {e['balance']:.2f} USD\n"
        f"{t_html(uid, 'otp_today')} {otp_today}\n"
        f"{t_html(uid, 'otp_all_time')} {otp_alltime}\n\n"
        f"{t_html(uid, 'language_current')}\n\n"
        f"{t_html(uid, 'profile_nav')}"
    )

    top_row = []
    if is_feature_enabled("balance"):
        top_row.append(mkbtn("balance_btn", "Balance", callback_data="profil_balance", style="success"))
    if is_feature_enabled("withdraw"):
        top_row.append(mkbtn("withdraw_btn", "Withdraw", callback_data="profil_withdraw", style="danger"))

    rows = []
    if top_row:
        rows.append(top_row)
    if is_feature_enabled("referral"):
        rows.append([mkbtn("referral_btn", "Referral", callback_data="profil_referral", style="success")])

    # Language switch button
    rows.append([mkbtn("lang_switch", t(uid, "switch_lang_btn").lstrip("🌐 ").strip(), callback_data="lang_switch", style="primary")])

    await update.effective_message.reply_text(
        msg, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_profil_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_balance(update, context)

async def cb_profil_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_withdraw(update, context)

async def cb_profil_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_referral(update, context)

# ─── BALANCE ───
async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    if not is_feature_enabled("balance"):
        return await update.effective_message.reply_text(feature_disabled_text("Balance"), parse_mode="HTML")
    uid = str(update.effective_user.id)
    e   = get_user_earnings(uid)
    pending = [w for w in withdrawals if w["userId"] == uid and w["status"] == "pending"]
    withdrawn = sum(w["amount"] for w in withdrawals if w["userId"] == uid and w["status"] == "approved")
    ref_count = users.get(uid, {}).get("referralCount", 0)
    ref_earn  = e.get("referralEarnings", 0)

    await update.effective_message.reply_text(
        f"💰 <b>Your Earnings</b>\n\n"
        f"💵 <b>Current Balance:</b> {e['balance']:.2f} USD\n"
        f"📈 <b>Total Earned:</b> {e['totalEarned']:.2f} USD\n"
        f"📨 <b>Total OTPs:</b> {e.get('otpCount', 0)}\n"
        f"💸 <b>Total Withdrawn:</b> {withdrawn:.2f} USD\n"
        f"⏳ <b>Pending Withdrawals:</b> {len(pending)}\n\n"
        f"👥 <b>Referrals:</b> {ref_count}\n"
        f"🎁 <b>Referral Earnings:</b> {ref_earn:.2f} USD\n\n"
        f"📌 <b>Minimum Withdraw:</b> {settings['minWithdraw']} USD",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("start_withdraw", "Withdraw", callback_data="start_withdraw", style="danger")],
            [mkbtn("withdraw_hist", "Withdraw History", callback_data="withdraw_history", style="danger")],
        ])
    )

# ─── REFERRAL ───
async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    if not is_feature_enabled("referral"):
        return await update.effective_message.reply_text(feature_disabled_text("Referral"), parse_mode="HTML")
    uid = str(update.effective_user.id)
    bot_username = context.bot.username
    ref_link = get_referral_link(uid, bot_username)
    commission = settings.get("referralCommission", 10)
    ref_count = users.get(uid, {}).get("referralCount", 0)
    ref_earn  = get_user_earnings(uid).get("referralEarnings", 0)

    referred_list = referrals.get(uid, [])
    referred_text = ""
    if referred_list:
        for r_uid in referred_list[-5:][::-1]:
            r_user = users.get(r_uid, {})
            r_name = html.escape(r_user.get("first_name", "User"))
            r_earn  = get_user_earnings(r_uid)
            my_cut  = round(r_earn.get("totalEarned", 0) * commission / 100, 2)
            referred_text += f"  👤 {r_name} — commission: <b>{my_cut:.2f} USD</b>\n"

    msg = (
        f"{t_html(uid, 'referral_title')}\n\n"
        f"{t_html(uid, 'your_ref_link')}\n<code>{html.escape(ref_link)}</code>\n\n"
        f"{t_html(uid, 'commission_rate', rate=commission)}\n\n"
        f"{t_html(uid, 'ref_stats_label')}\n"
        f"{t_html(uid, 'ref_count_label')} <b>{ref_count}</b>\n"
        f"{t_html(uid, 'ref_earn_label')} <b>{ref_earn:.2f} USD</b>\n"
    )
    if referred_text:
        msg += f"\n?? <b>Recent Referrals:</b>\n{referred_text}"

    msg += "\n" + t_html(uid, "ref_how", rate=commission)

    share_text = "Join this bot and earn from OTPs!" if get_user_lang(uid) == "en" else "Bergabunglah dan dapatkan penghasilan dari OTP!"
    await update.effective_message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("share_link", "Share Referral Link", url=f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}", style="success")],
            [mkbtn("ref_stats", "Referral Stats", callback_data="ref_stats", style="success")],
        ])
    )

async def cb_ref_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    commission = settings.get("referralCommission", 10)
    ref_count = users.get(uid, {}).get("referralCount", 0)
    ref_earn  = get_user_earnings(uid).get("referralEarnings", 0)
    referred_list = referrals.get(uid, [])

    msg = (
        f"📊 <b>Referral Statistics</b>\n\n"
        f"👥 <b>Total Referred:</b> {ref_count}\n"
        f"💰 <b>Total Commission:</b> {ref_earn:.2f} USD\n"
        f"📌 <b>Commission Rate:</b> {commission}%\n\n"
    )

    if referred_list:
        msg += "👤 <b>All Referred Users:</b>\n"
        for r_uid in referred_list[-20:]:
            r_user = users.get(r_uid, {})
            r_name = html.escape(r_user.get("first_name", "User"))
            r_earn = get_user_earnings(r_uid)
            otps   = r_earn.get("otpCount", 0)
            my_cut = round(r_earn.get("totalEarned", 0) * commission / 100, 2)
            msg += f"  • {r_name} | OTPs: {otps} | Your cut: {my_cut:.2f}$\n"
    else:
        msg += "<i>No referrals yet.</i>\n"

    if len(msg) > 4000:
        msg = msg[:3950] + "\n...<i>truncated</i>"

    bot_username = context.bot.username
    ref_link = get_referral_link(uid, bot_username)

    await query.edit_message_text(
        msg, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("share_link", "Share Link", url=f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}", style="success")],
            [mkbtn("back", "Back", callback_data="goto_main", style="primary")],
        ])
    )

# ─── WITHDRAW ───
async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    uid = str(update.effective_user.id)
    e   = get_user_earnings(uid)
    sess = get_session(uid)
    sess["state"] = None

    if not settings.get("withdrawEnabled", True):
        return await update.effective_message.reply_text("⏸️ <b>Withdrawals are currently disabled.</b>", parse_mode="HTML")

    if e["balance"] < settings["minWithdraw"]:
        return await update.effective_message.reply_text(
            f"❌ <b>Insufficient balance.</b>\n\n"
            f"💵 Balance: {e['balance']:.2f} USD\n"
            f"📌 Minimum: {settings['minWithdraw']} USD",
            parse_mode="HTML"
        )

    await update.effective_message.reply_text(
        f"💸 <b>Withdraw</b>\n\n💵 Balance: <b>{e['balance']:.2f} USD</b>\n\nChoose method:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("wm_bkash", "bKash", callback_data="wm:bKash", style="success"),
             mkbtn("wm_nagad", "Nagad", callback_data="wm:Nagad", style="success")],
            [mkbtn("w_cancel", "Cancel", callback_data="w_cancel", style="danger")],
        ])
    )

async def cb_withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split(":", 1)[1]
    uid    = str(update.effective_user.id)
    sess   = get_session(uid)
    e      = get_user_earnings(uid)

    sess["state"] = "w_amount"
    sess["data"]  = {"method": method}

    amounts = []
    for a in [settings["minWithdraw"], 100, 200, 500]:
        if e["balance"] >= a and a not in amounts:
            amounts.append(a)

    rows = []
    for i in range(0, len(amounts), 2):
        row = [mkbtn("start_withdraw", f"{amounts[i]} USD", callback_data=f"wa:{method}:{amounts[i]}", style="success")]
        if i+1 < len(amounts):
            row.append(mkbtn("start_withdraw", f"{amounts[i+1]} USD", callback_data=f"wa:{method}:{amounts[i+1]}", style="success"))
        rows.append(row)
    rows.append([mkbtn("balance_btn", f"All ({e['balance']:.2f} USD)", callback_data=f"wa:{method}:{e['balance']:.2f}", style="success")])
    rows.append([mkbtn("w_cancel", "Cancel", callback_data="w_cancel", style="danger")])

    icon = "🟣" if method == "bKash" else "🟠"
    await query.edit_message_text(
        f"{icon} <b>{html.escape(method)} Withdrawal</b>\n\n💵 Balance: <b>{e['balance']:.2f} USD</b>\n\nSelect amount or type in chat:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, method, amt_str = query.data.split(":")
    amount = float(amt_str)
    uid    = str(update.effective_user.id)
    sess   = get_session(uid)
    e      = get_user_earnings(uid)

    if amount < settings["minWithdraw"]:
        return await query.answer(f"❌ Minimum {settings['minWithdraw']} USD", show_alert=True)
    if amount > e["balance"]:
        return await query.answer("❌ Insufficient balance!", show_alert=True)

    sess["state"] = "w_account"
    sess["data"]  = {"method": method, "amount": amount}
    icon = "🟣" if method == "bKash" else "🟠"

    await query.edit_message_text(
        f"{icon} <b>{html.escape(method)} — {amount:.2f} USD</b>\n\n📱 Your <b>{html.escape(method)} number:</b>\nExample: <code>01712345678</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("w_cancel", "Cancel", callback_data="w_cancel", style="danger")]])
    )

async def cb_withdraw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None
    sess["data"]  = None
    await query.edit_message_text("❌ <b>Cancelled.</b>", parse_mode="HTML")

async def cb_withdraw_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = str(update.effective_user.id)
    uwith = [w for w in withdrawals if w["userId"] == uid][-10:][::-1]

    text = "📋 <b>Withdraw History</b>\n\n"
    if not uwith:
        text += "No withdrawal requests yet."
    else:
        for w in uwith:
            icon = "✅" if w["status"] == "approved" else "❌" if w["status"] == "rejected" else "⏳"
            date = html.escape(w["requestedAt"][:10])
            text += f"{icon} <b>{w['amount']:.2f} USD</b> - {html.escape(w['method'])}\n"
            text += f"📱 <code>{html.escape(w['account'])}</code> | {date}\n\n"

    await query.edit_message_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("back", "Back", callback_data="goto_main", style="primary")]]))

async def cb_start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    e    = get_user_earnings(uid)
    sess = get_session(uid)
    sess["state"] = None
    sess["data"]  = None

    if not settings.get("withdrawEnabled", True):
        return await query.edit_message_text("⏸️ <b>Withdrawals are currently disabled.</b>", parse_mode="HTML")
    if e["balance"] < settings["minWithdraw"]:
        return await query.edit_message_text(
            f"❌ <b>Insufficient balance.</b>\n💵 Balance: {e['balance']:.2f} USD\n📌 Minimum: {settings['minWithdraw']} USD",
            parse_mode="HTML"
        )

    await query.edit_message_text(
        f"💸 <b>Withdraw</b>\n\n💵 Balance: <b>{e['balance']:.2f} USD</b>\n\nChoose method:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("wm_bkash", "bKash", callback_data="wm:bKash", style="success"),
             mkbtn("wm_nagad", "Nagad", callback_data="wm:Nagad", style="success")],
            [mkbtn("w_cancel", "Cancel", callback_data="w_cancel", style="danger")],
        ])
    )

# ─── WhatsApp Connect ───
async def cb_wa_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)

    if wa_sessions.get(uid, {}).get("connected"):
        await query.edit_message_text(
            "✅ <b>WhatsApp Already Connected!</b>\n\n"
            "🟢 WhatsApp is currently active.\n"
            "Press the button below to disconnect:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [mkbtn("wa_disconnect", "Logout / Disconnect", callback_data="wa_disconnect", style="danger")],
                [mkbtn("wa_status", "Check Status", callback_data="wa_status", style="primary")],
            ])
        )
        return

    sess = get_session(uid)
    sess["state"] = "wa_waiting_number"
    await context.bot.send_message(
        update.effective_user.id,
        "📱 <b>WhatsApp Connect</b>\n\nEnter your WhatsApp number (with country code):\nExample: <code>8801712345678</code>"
    )

async def cb_wa_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Checking...")
    uid   = str(update.effective_user.id)

    try:
        state = await green_get_state(uid)
    except:
        state = "notAuthorized"

    conn = (state == "authorized")
    if conn:
        wa_sessions[uid] = {"connected": True}
    else:
        wa_sessions.pop(uid, None)

    STATE_MAP = {
        "authorized":    "✅ <b>WhatsApp Connected!</b>\n\n📱/❌ will appear when a number is assigned.",
        "notAuthorized": "🔴 <b>WhatsApp not connected.</b>\n\nAfter entering the code, press Check Status again.",
    }
    text = STATE_MAP.get(state, f"❓ Unknown state: {state}")
    btns = [[mkbtn("wa_disconnect", "Disconnect", callback_data="wa_disconnect", style="danger")]] if conn else \
           [[mkbtn("wa_connect", "Connect", callback_data="wa_connect", style="success")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def cb_wa_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Disconnecting...")
    uid = str(update.effective_user.id)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: baileys_request("POST", "/disconnect", {"userId": uid}))
        logger.info(f"✅ Baileys logout called for uid={uid}")
    except Exception as e:
        logger.error(f"Baileys logout error: {e}")

    wa_sessions.pop(uid, None)

    await query.edit_message_text(
        "🔴 <b>WhatsApp Disconnected!</b>\n\n"
        "Your WhatsApp has been successfully logged out.\n"
        "Press the button below to reconnect:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("wa_connect", "Connect WhatsApp", callback_data="wa_connect", style="success")],
        ])
    )

# ─── TOOLS (menu gabungan: Get Tempmail + 2FA + Cek Bio WA + FIX Merah) ───
async def handle_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    rows = []
    if is_feature_enabled("tempmail"):
        rows.append([mkbtn("tempmail", "Get Tempmail", callback_data="tools_tempmail", style="success")])
    if is_feature_enabled("twofa"):
        rows.append([mkbtn("twofa", "2FA", callback_data="tools_2fa", style="success")])

    # Tombol Cek Bio WA — redirect ke link tersendiri
    cek_bio_url = settings.get("cek_bio_wa_url", "")
    if is_feature_enabled("cek_bio_wa") and cek_bio_url:
        rows.append([mkbtn("cek_bio_wa", "Cek Bio WA", url=cek_bio_url, style="primary")])

    # Tombol FIX Merah — redirect ke link tersendiri
    fix_merah_url = settings.get("fix_merah_url", "")
    if is_feature_enabled("fix_merah") and fix_merah_url:
        rows.append([mkbtn("fix_merah", "FIX Merah", url=fix_merah_url, style="danger")])

    uid2 = str(update.effective_user.id) if update.effective_user else "0"
    if not rows:
        await send_bottom_menu(context, update.effective_chat.id, uid2)
        return await update.effective_message.reply_text(
            t(uid2, "tools_unavailable"),
            parse_mode="HTML"
        )

    await update.effective_message.reply_text(
        t(uid2, "tools_title"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_tools_tempmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_tempmail(update, context)

async def cb_tools_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_2fa(update, context)

# ─── Temp Mail ───
async def handle_tempmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    if not is_feature_enabled("tempmail"):
        return await update.effective_message.reply_text(feature_disabled_text("Get Tempmail"), parse_mode="HTML")
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None
    existing = temp_mails.get(uid)

    if existing:
        await update.effective_message.reply_text(
            f"📧 <b>Temporary Email</b>\n\n📌 Your email:\n`{existing['address']}`",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [mkbtn("tm_check_inbox", "Check Inbox", callback_data="tm_inbox", style="primary")],
                [mkbtn("tm_show", "Show Email", callback_data="tm_show", style="primary")],
                [mkbtn("tm_new_email", "Get New Email", callback_data="tm_create", style="primary")],
                [mkbtn("tm_delete", "Delete Email", callback_data="tm_delete", style="danger")],
            ])
        )
    else:
        await update.effective_message.reply_text(
            "📧 <b>Temporary Email</b>\n\n✅ Create a new disposable email address.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[mkbtn("tm_create", "Create New Email", callback_data="tm_create", style="success")]])
        )

async def cb_tm_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Creating...")
    uid   = str(update.effective_user.id)
    loading = await context.bot.send_message(uid, "⏳ <b>Creating your email...</b>", parse_mode="HTML")

    async def _create_task():
        try:
            new_email = await create_fresh_email()
            if not new_email:
                await context.bot.edit_message_text(
                    "❌ <b>Email creation failed.</b> Please try again.",
                    chat_id=uid, message_id=loading.message_id,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[mkbtn("tm_retry", "Retry", callback_data="tm_create", style="primary")]])
                )
                return
            temp_mails[uid] = new_email
            save_temp_mails()
            await context.bot.edit_message_text(
                f"✅ <b>New Email Created!</b>\n\n📧 `{new_email['address']}`\n\n📌 Use this on any website.",
                chat_id=uid, message_id=loading.message_id,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [mkbtn("tm_check_inbox", "Check Inbox", callback_data="tm_inbox", style="primary")],
                    [mkbtn("tm_new_email", "Get New Email", callback_data="tm_create", style="primary")],
                    [mkbtn("tm_delete", "Delete", callback_data="tm_delete", style="danger")],
                ])
            )
        except Exception as e:
            logger.error(f"cb_tm_create task error uid={uid}: {e}")
            try:
                await context.bot.edit_message_text(
                    "❌ <b>Error occurred.</b> Please try again.",
                    chat_id=uid, message_id=loading.message_id,
                    parse_mode="HTML"
                )
            except:
                pass

    asyncio.create_task(_create_task())

async def cb_tm_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📬 Loading...")
    uid = str(update.effective_user.id)

    if uid not in temp_mails:
        return await query.edit_message_text(
            "❌ No email found.",
            reply_markup=InlineKeyboardMarkup([[mkbtn("tm_create", "Create", callback_data="tm_create", style="success")]])
        )

    email_obj = temp_mails[uid]

    async def _inbox_task():
        try:
            messages  = await get_email_inbox(email_obj)
            now_str   = now_wib().strftime("%I:%M:%S %p")
            text      = f"📬 <b>Inbox:</b> `{email_obj['address']}`\n🕐 _{now_str}_\n\n"

            if not messages:
                text += "📭 <b>No emails yet.</b>"
            else:
                for msg in messages[:5]:
                    text += f"━━━━━━━━━━\n📩 <b>From:</b> {msg['from']}\n📌 <b>Subject:</b> {msg['subject']}\n"
                    body = await get_email_message(msg["id"], email_obj)
                    if body:
                        otp_m = re.findall(r"\b\d{4,8}\b", body)
                        if otp_m:
                            text += f"\n🔑 <b>OTP:</b> `{otp_m[0]}`\n"
                        text += f"\n📝 _{body[:250]}..._\n" if len(body) > 250 else f"\n📝 _{body}_\n"
                    text += "\n"

            try:
                await query.edit_message_text(text[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                    [mkbtn("refresh", "Refresh", callback_data="tm_inbox", style="primary")],
                    [mkbtn("tm_new_email", "New Email", callback_data="tm_create", style="primary")],
                    [mkbtn("tm_delete", "Delete", callback_data="tm_delete", style="danger")],
                ]))
            except:
                pass
        except Exception as e:
            logger.error(f"cb_tm_inbox task error uid={uid}: {e}")

    asyncio.create_task(_inbox_task())

async def cb_tm_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    if uid not in temp_mails:
        return await query.answer("❌ No email found", show_alert=True)
    addr = temp_mails[uid]["address"]
    await query.edit_message_text(
        f"📧 <b>Your Temp Email:</b>\n\n`{addr}`",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("tm_check_inbox", "Check Inbox", callback_data="tm_inbox", style="primary")],
            [mkbtn("tm_new_email", "New Email", callback_data="tm_create", style="primary")],
        ])
    )

async def cb_tm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    temp_mails.pop(uid, None)
    save_temp_mails()
    await query.edit_message_text("✅ <b>Email deleted.</b>", parse_mode="HTML")

# ─── 2FA/TOTP ───
async def handle_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context): return
    if not is_feature_enabled("twofa"):
        return await update.effective_message.reply_text(feature_disabled_text("2FA"), parse_mode="HTML")
    sess = get_session(str(update.effective_user.id))
    sess["state"] = None
    await update.effective_message.reply_text(
        "🔐 <b>2-Step Verification Code Generator</b>\n\nSelect a service:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("totp_facebook", "Facebook 2FA", callback_data="totp:facebook", style="success")],
            [mkbtn("totp_instagram", "Instagram 2FA", callback_data="totp:instagram", style="success")],
            [mkbtn("totp_google", "Google 2FA", callback_data="totp:google", style="success")],
            [mkbtn("totp_other", "Other 2FA", callback_data="totp:other", style="success")],
        ])
    )

async def cb_totp_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    svc  = query.data.split(":", 1)[1]
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = "totp_waiting_secret"
    sess["data"]  = {"service": svc}

    if uid in users:
        users[uid]["pending_totp_svc"] = svc
        await async_save_users()

    icons = {"facebook": "📘", "instagram": "📸", "google": "🔍", "other": "⚙️"}
    names = {"facebook": "Facebook", "instagram": "Instagram", "google": "Google", "other": "Other"}
    icon  = icons.get(svc, "🔐")
    name  = names.get(svc, svc)

    await query.edit_message_text(
        f"{icon} <b>{name} Secret Key</b>\n\n"
        f"Send your Authenticator Secret Key.\n\n"
        f"🔑 It looks like: <code>JBSWY3DPEHPK3PXP</code>\n\n"
        f"Type /cancel to cancel",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("totp_cancel", "Cancel", callback_data="totp_back", style="danger")]])
    )

async def cb_totp_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔐 <b>2FA Code Generator</b>\n\nSelect a service:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("totp_facebook", "Facebook 2FA", callback_data="totp:facebook", style="success")],
            [mkbtn("totp_instagram", "Instagram 2FA", callback_data="totp:instagram", style="success")],
            [mkbtn("totp_google", "Google 2FA", callback_data="totp:google", style="success")],
            [mkbtn("totp_other", "Other 2FA", callback_data="totp:other", style="success")],
        ])
    )

async def cb_totp_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Refreshing...")
    _, svc, secret_enc = query.data.split(":", 2)

    if secret_enc == "TOOLONG":
        await query.edit_message_text(
            "⚠️ The secret key is too long. To refresh, go to 🛠️ Tools → 🔐 2FA and try again.",
            reply_markup=InlineKeyboardMarkup([[mkbtn("totp_back", "Back", callback_data="totp_back", style="primary")]]))
        return

    secret = urllib.parse.unquote(secret_enc)
    result = generate_totp(secret)

    icons = {"facebook": "📘", "instagram": "📸", "google": "🔍", "other": "⚙️"}
    names = {"facebook": "Facebook", "instagram": "Instagram", "google": "Google", "other": "2FA"}
    icon  = icons.get(svc, "🔐")
    name  = names.get(svc, svc)

    if not result:
        return await query.edit_message_text("❌ Invalid secret key.", parse_mode="HTML")

    cb_data = f"totp_r:{svc}:{secret_enc}"

    try:
        await query.edit_message_text(
            f"{icon} <b>{name} 2FA Code</b>\n\n"
            f"🔑 <b>Code:</b> `{result['token']}`\n\n"
            f"⏰ <b>{result['timeRemaining']} seconds remaining</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [mkbtn("totp_refresh", "Refresh Code", callback_data=cb_data, style="primary")],
                [mkbtn("totp_back", "Back", callback_data="totp_back", style="primary")],
            ])
        )
    except:
        pass

# ─── Support ───
async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_feature_enabled("support"):
        return await update.effective_message.reply_text(feature_disabled_text("Support"), parse_mode="HTML")
    await update.effective_message.reply_text(
        "💬 <b>Support</b>\n\nContact admin:\n📌 @pr1nceyuma",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("contact_admin", "Contact", url="https://t.me/pr1nceyuma", style="success")]])
    )

async def handle_minimize_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sembunyikan menu bawah (reply keyboard). Menu bisa dimunculkan lagi
    lewat tombol '?? Tampilkan Menu' di bawah pesan ini, atau kirim /menu."""
    uid = str(update.effective_user.id)
    await update.effective_message.reply_text(
        t_html(uid, "menu_minimized"),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.effective_message.reply_text(
        "👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(uid, "menu_restore_btn"), callback_data="show_bottom_menu")]
        ]),
    )

async def cb_show_bottom_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore the bottom reply keyboard after it's been minimized."""
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_bottom_menu(context, update.effective_chat.id, uid)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/menu — always-available way to bring the bottom menu back."""
    uid = str(update.effective_user.id)
    await send_bottom_menu(context, update.effective_chat.id, uid)

# ─── Admin Callbacks ───
async def cb_admin_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    report = "📊 <b>Stock Report</b>\n\n"
    total_all = 0
    for cc, svcs in numbers_by_cs.items():
        country = countries.get(cc, {"flag": "🏴", "name": cc})
        report += f"\n{get_country_flag_html(cc)} {html.escape(str(country.get('name', cc)))} (+{html.escape(str(cc))}):\n"
        ct = 0
        for svc_id, nums in svcs.items():
            svc = services.get(svc_id, {"icon": "📞", "name": svc_id})
            if nums:
                report += f"  {get_svc_icon_html(svc_id)} {html.escape(str(svc.get('name', svc_id)))}: <b>{len(nums)}</b>\n"
                ct += len(nums)
        report += f"  <b>Total:</b> {ct}\n"
        total_all += ct

    report += f"\n📈 <b>Grand Total:</b> {total_all}\n"
    report += f"👥 <b>Active:</b> {len(active_numbers)}\n"
    report += f"📨 <b>OTPs:</b> {len(otp_log)}"

    if len(report) > 4000:
        report = report[:3950] + "\n...<i>truncated</i>"

    await safe_edit(query, report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [mkbtn("admin_refresh", "Refresh", callback_data="admin_stock", style="primary")],
        [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
    ]))

# ─── Live Traffic Monitor ───
def _traffic_level(rank, count):
    """Beri label sesuai peringkat & jumlah permintaan."""
    if count <= 0:
        return "⚪ Sepi"
    if rank == 0:
        return "🔥 HIGH"
    if rank <= 2:
        return "🟡 Sedang"
    return "🟢 Normal"

def _compute_traffic(window_hours):
    cutoff = now_wib() - timedelta(hours=window_hours)
    svc_count, cc_count, combo_count = {}, {}, {}
    for log in otp_log:
        ts = log.get("timestamp")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts)
        except Exception:
            continue
        if t < cutoff:
            continue
        svc_id = log.get("service") or "unknown"
        cc = log.get("countryCode") or "?"
        svc_count[svc_id] = svc_count.get(svc_id, 0) + 1
        cc_count[cc] = cc_count.get(cc, 0) + 1
        combo_count[(svc_id, cc)] = combo_count.get((svc_id, cc), 0) + 1
    return svc_count, cc_count, combo_count

def _build_traffic_report(admin: bool):
    """Bangun teks Live Traffic (HTML). admin=True menampilkan info stok & peringatan restock,
    admin=False menampilkan versi ramah user dengan rekomendasi beli."""
    svc_count, cc_count, combo_count = _compute_traffic(window_hours=1)
    svc_count_24h, cc_count_24h, _ = _compute_traffic(window_hours=24)

    top_svc = sorted(svc_count.items(), key=lambda x: x[1], reverse=True)[:5]
    top_cc = sorted(cc_count.items(), key=lambda x: x[1], reverse=True)[:5]
    top_combo = sorted(combo_count.items(), key=lambda x: x[1], reverse=True)[:5]

    now_str = now_wib().strftime("%H:%M:%S")
    report = f"🔥 <b>Live Traffic Monitor</b>\n<i>Update terakhir: {now_str} • window 1 jam</i>\n\n"

    report += "📞 <b>Service Paling Ramai (1 jam)</b>\n"
    if not top_svc:
        report += "  <i>Belum ada aktivitas dalam 1 jam terakhir.</i>\n"
    for i, (svc_id, cnt) in enumerate(top_svc):
        svc = services.get(svc_id, {"icon": "📞", "name": svc_id})
        report += f"  {_traffic_level(i, cnt)} {get_svc_icon_html(svc_id)} <b>{html.escape(svc['name'])}</b> — {cnt} OTP/jam (24j: {svc_count_24h.get(svc_id,0)})\n"

    report += "\n🌍 <b>Negara Paling Ramai (1 jam)</b>\n"
    if not top_cc:
        report += "  <i>Belum ada aktivitas dalam 1 jam terakhir.</i>\n"
    for i, (cc, cnt) in enumerate(top_cc):
        country = countries.get(cc, {"flag": "🏴", "name": cc})
        report += f"  {_traffic_level(i, cnt)} {get_country_flag_html(cc)} <b>{html.escape(country['name'])}</b> (+{cc}) — {cnt} OTP/jam (24j: {cc_count_24h.get(cc,0)})\n"

    report += "\n⚡ <b>Kombinasi Paling Diburu</b>\n"
    if not top_combo:
        report += "  <i>Belum ada data kombinasi.</i>\n"
    for (svc_id, cc), cnt in top_combo:
        svc = services.get(svc_id, {"icon": "📞", "name": svc_id})
        country = countries.get(cc, {"flag": "🏴", "name": cc})
        stock = len(numbers_by_cs.get(cc, {}).get(svc_id, []))
        if admin:
            warn = " ⚠️ <b>STOK MENIPIS</b>" if stock <= 3 else ""
            report += f"  {get_svc_icon_html(svc_id)} {html.escape(svc['name'])} × {get_country_flag_html(cc)} {html.escape(country['name'])}: {cnt}x{warn} <i>(stok: {stock})</i>\n"
        else:
            ready = "✅ Ready" if stock > 0 else "⏳ Kosong"
            report += f"  {get_svc_icon_html(svc_id)} {html.escape(svc['name'])} × {get_country_flag_html(cc)} {html.escape(country['name'])}: {cnt}x <i>({ready})</i>\n"

    if admin:
        low_stock_alerts = []
        for svc_id, cnt in top_svc:
            for cc, _ in top_cc:
                stock = len(numbers_by_cs.get(cc, {}).get(svc_id, []))
                if cnt >= 2 and stock <= 3:
                    svc = services.get(svc_id, {"icon": "📞", "name": svc_id})
                    country = countries.get(cc, {"flag": "🏴", "name": cc})
                    low_stock_alerts.append(f"  🔴 {get_svc_icon_html(svc_id)} {html.escape(svc['name'])} — {get_country_flag_html(cc)} {html.escape(country['name'])} (stok: {stock})")
        if low_stock_alerts:
            report += "\n🚨 <b>Perlu Restock Segera</b>\n" + "\n".join(low_stock_alerts[:5]) + "\n"
    else:
        if top_svc:
            best_svc_id = top_svc[0][0]
            best_svc = services.get(best_svc_id, {"icon": "📞", "name": best_svc_id})
            report += f"\n💡 <b>Rekomendasi:</b> {get_svc_icon_html(best_svc_id)} <b>{html.escape(best_svc['name'])}</b> lagi paling gacor sekarang, buruan ambil sebelum kehabisan! 🚀\n"

    if len(report) > 4000:
        report = report[:3950] + "\n...<i>truncated</i>"

    return report, (top_svc[0][0] if top_svc else None)

async def cb_admin_live_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    report, _ = _build_traffic_report(admin=True)

    await safe_edit(query, report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [mkbtn("admin_refresh", "Refresh", callback_data="admin_live_traffic", style="success")],
        [mkbtn("live_stock", "Stock Report", callback_data="admin_stock", style="success")],
        [mkbtn("admin_back", "Back", callback_data="admin_back", style="danger")],
    ]))

def _user_traffic_keyboard(best_svc_id):
    rows = []
    if best_svc_id:
        svc = services.get(best_svc_id, {"icon": "📞", "name": best_svc_id})
        rows.append([mkbtn("a_add_numbers", f"{svc['name']} Sekarang", callback_data=f"svc:{best_svc_id}", style="success")])
    rows.append([mkbtn("live_refresh", "Refresh", callback_data="user_live_traffic", style="primary")])
    return InlineKeyboardMarkup(rows)

async def handle_live_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_feature_enabled("livetraffic"):
        return await update.effective_message.reply_text(feature_disabled_text("Live Traffic"), parse_mode="HTML")
    if not await ensure_verified(update, context):
        return
    report, best_svc_id = _build_traffic_report(admin=False)
    try:
        await update.effective_message.reply_text(report, parse_mode="HTML", reply_markup=_user_traffic_keyboard(best_svc_id))
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        await update.effective_message.reply_text(_strip_tg_emoji_tags(report), parse_mode="HTML", reply_markup=_user_traffic_keyboard(best_svc_id))

async def cb_user_live_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Diperbarui")
    report, best_svc_id = _build_traffic_report(admin=False)
    await safe_edit(query, report, parse_mode="HTML", reply_markup=_user_traffic_keyboard(best_svc_id))

async def cb_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    try:
        total = len(users)
        total_referrals = sum(u.get("referralCount", 0) for u in users.values())
        msg   = (
            f"👥 <b>User Statistics</b>\n\n"
            f"• Total Users: {total}\n"
            f"• Active Numbers: {len(active_numbers)}\n"
            f"• OTPs Processed: {len(otp_log)}\n"
            f"• Total Referrals Made: {total_referrals}\n\n"
        )

        recent = sorted(users.values(), key=lambda u: u.get("last_active",""), reverse=True)[:10]
        for u in recent:
            uid_str  = u.get('id', '?')
            fname    = u.get('first_name', '').replace('*','').replace('_','').replace('`','')
            uname    = u.get('username', 'no_username').replace('_','\\_')
            msg += f"👤 <b>{fname}</b>\n🆔 `{uid_str}` | @{uname}\n"
            msg += f"🕐 {get_time_ago(u.get('last_active', ''))}\n\n"

        if len(msg) > 4000:
            msg = msg[:3950] + "...<i>truncated</i>"

        await safe_edit(query, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [mkbtn("admin_refresh", "Refresh", callback_data="admin_users", style="primary")],
            [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
        ]))
    except Exception as e:
        logger.error(f"cb_admin_users error: {e}", exc_info=True)
        try:
            await query.edit_message_text(
                f"❌ <b>Error loading user stats</b>\n\n`{str(e)[:200]}`",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")]])
            )
        except:
            pass

async def cb_admin_otp_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    msg = "📋 <b>Recent OTP Logs</b>\n\n"
    if not otp_log:
        msg += "No OTPs yet."
    else:
        for log in otp_log[-10:][::-1]:
            msg += f"📞 `{log['phoneNumber']}<code> → 👤 </code>{log['userId']}`\n"
            msg += f"🕐 {get_time_ago(log.get('timestamp',''))}\n\n"

    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [mkbtn("admin_refresh", "Refresh", callback_data="admin_otp_log", style="primary")],
        [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
    ]))

# ─── 🔥 DASHBOARD STATISTIK ───
def _dash_parse_ts(log: dict):
    """Parse timestamp OTP log jadi datetime naive (biar gampang dibandingkan)."""
    ts = log.get("timestamp", "")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None

def _dash_source_label(log: dict) -> str:
    src = log.get("source")
    if not src:
        return "✈️ Telegram Group"
    if src == "http_api":
        return "🌐 HTTP API"
    if src.startswith("panel_"):
        return f"📡 {src[len('panel_'):]}"
    return src

def _dash_bar_chart(data, max_width=18, bar_char="▇"):
    """data: list of (label, value). Render sebagai ASCII bar chart untuk pesan HTML.
    CATATAN: sebelumnya label dibungkus backtick ` `label` ` — itu sintaks Markdown,
    padahal semua pesan dashboard dikirim dengan parse_mode="HTML" sehingga backtick-nya
    tampil literal (bukan code format). Diganti ke tag <code> yang benar untuk HTML,
    plus escape supaya label yang mengandung custom emoji (<tg-emoji>) tetap valid."""
    if not data or all(v == 0 for _, v in data):
        return "<i>Belum ada data OTP untuk periode ini.</i>"
    max_val = max(v for _, v in data) or 1
    lines = []
    for label, val in data:
        bar_len = round((val / max_val) * max_width) if max_val > 0 else 0
        bar = bar_char * bar_len if bar_len > 0 else "▏"
        label_str = str(label)
        lines.append(f"{label_str:<8}{bar} {val}")
    return "\n".join(lines)

def _dash_period_counts(period: str, n: int):
    """Hitung jumlah OTP per periode ('hour'/'day'/'month') untuk n periode terakhir
    (kronologis, termasuk periode kosong = 0)."""
    now = now_wib()
    buckets = {}
    for log in otp_log:
        dt = _dash_parse_ts(log)
        if not dt:
            continue
        if period == "hour":
            key = dt.strftime("%Y-%m-%d %H")
        elif period == "day":
            key = dt.strftime("%Y-%m-%d")
        else:
            key = dt.strftime("%Y-%m")
        buckets[key] = buckets.get(key, 0) + 1

    result = []
    for i in range(n - 1, -1, -1):
        if period == "hour":
            t = now - timedelta(hours=i)
            key   = t.strftime("%Y-%m-%d %H")
            label = t.strftime("%H:00")
        elif period == "day":
            t = now - timedelta(days=i)
            key   = t.strftime("%Y-%m-%d")
            label = t.strftime("%d/%m")
        else:
            y, m = now.year, now.month - i
            while m <= 0:
                m += 12
                y -= 1
            key   = f"{y:04d}-{m:02d}"
            label = datetime(y, m, 1).strftime("%b %y")
        result.append((label, buckets.get(key, 0)))
    return result

def _dash_top_counts(field_fn, top_n=8):
    """Hitung top-N kemunculan berdasarkan field_fn(log) -> label string."""
    counts = {}
    for log in otp_log:
        label = field_fn(log)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return ranked

def _dash_back_kb(extra_row=None):
    rows = []
    if extra_row:
        rows.append(extra_row)
    rows.append([mkbtn("admin_back", "Dashboard", callback_data="admin_dashboard", style="primary")])
    return InlineKeyboardMarkup(rows)

async def cb_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    now = now_wib()
    today_key = now.strftime("%Y-%m-%d")
    month_key = now.strftime("%Y-%m")
    week_ago  = now - timedelta(days=7)

    total_today = total_month = total_week = total_all = 0
    for log in otp_log:
        dt = _dash_parse_ts(log)
        total_all += 1
        if not dt:
            continue
        if dt.strftime("%Y-%m-%d") == today_key:
            total_today += 1
        if dt.strftime("%Y-%m") == month_key:
            total_month += 1
        if dt >= week_ago:
            total_week += 1

    top_panel   = _dash_top_counts(_dash_source_label, 1)
    top_country = _dash_top_counts(lambda l: countries.get(l.get("countryCode",""), {}).get("name"), 1)
    top_app     = _dash_top_counts(lambda l: services.get(l.get("service",""), {}).get("name"), 1)

    msg = (
        "🔥 <b>Dashboard Statistik</b>\n\n"
        f"📨 OTP Hari Ini: <b>{total_today}</b>\n"
        f"📨 OTP 7 Hari Terakhir: <b>{total_week}</b>\n"
        f"📨 OTP Bulan Ini: <b>{total_month}</b>\n"
        f"📨 Total Tercatat: <b>{total_all}</b> <i>(log tersimpan)</i>\n\n"
        f"🖥️ Panel Paling Aktif: <b>{top_panel[0][0] if top_panel else '-'}</b>\n"
        f"🌍 Negara Terbanyak: <b>{top_country[0][0] if top_country else '-'}</b>\n"
        f"📱 Aplikasi Terbanyak: <b>{top_app[0][0] if top_app else '-'}</b>\n\n"
        "Pilih statistik detail di bawah 👇"
    )

    buttons = [
        [mkbtn("a_dash_hourly", "OTP per Jam", callback_data="dash_hourly", style="success"),
         mkbtn("a_dash_daily", "OTP per Hari", callback_data="dash_daily", style="success")],
        [mkbtn("a_dash_monthly", "OTP per Bulan", callback_data="dash_monthly", style="success"),
         mkbtn("a_dash_growth", "Grafik Pertumbuhan", callback_data="dash_growth", style="success")],
        [mkbtn("a_dash_panels", "Panel Paling Aktif", callback_data="dash_panels", style="success"),
         mkbtn("a_dash_countries", "Negara Terbanyak", callback_data="dash_countries", style="success")],
        [mkbtn("a_dash_apps", "Aplikasi Terbanyak", callback_data="dash_apps", style="success")],
        [mkbtn("admin_refresh", "Refresh", callback_data="admin_dashboard", style="primary")],
        [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
    ]
    await safe_edit(query, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cb_dash_hourly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    data = _dash_period_counts("hour", 24)
    msg = "⏰ <b>OTP per Jam (24 jam terakhir)</b>\n\n" + _dash_bar_chart(data)
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_hourly", style="primary")]))

async def cb_dash_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    data = _dash_period_counts("day", 14)
    msg = "📅 <b>OTP per Hari (14 hari terakhir)</b>\n\n" + _dash_bar_chart(data)
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_daily", style="primary")]))

async def cb_dash_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    data = _dash_period_counts("month", 12)
    msg = "🗓️ <b>OTP per Bulan (12 bulan terakhir)</b>\n\n" + _dash_bar_chart(data)
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_monthly", style="primary")]))

async def cb_dash_growth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    data = _dash_period_counts("day", 14)

    this_week = sum(v for _, v in data[-7:])
    last_week = sum(v for _, v in data[-14:-7])
    if last_week > 0:
        pct = (this_week - last_week) / last_week * 100
        trend = f"📈 +{pct:.1f}%" if pct >= 0 else f"📉 {pct:.1f}%"
    else:
        trend = "📈 +100%" if this_week > 0 else "➖ 0%"

    msg = (
        "📈 <b>Grafik Pertumbuhan OTP</b>\n\n"
        + _dash_bar_chart(data)
        + f"\n\n📊 Minggu ini: *{this_week}<b> vs minggu lalu: </b>{last_week}*\n"
        f"Tren: <b>{trend}</b>"
    )
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_growth", style="primary")]))

async def cb_dash_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    ranked = _dash_top_counts(_dash_source_label, 10)
    msg = "🖥️ <b>Panel Paling Aktif</b>\n\n" + _dash_bar_chart(ranked)
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_panels", style="primary")]))

async def cb_dash_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    def _cc_label(l):
        cc = l.get("countryCode", "")
        c  = countries.get(cc)
        return f"{get_country_flag_html(cc)} {html.escape(str(c.get('name', cc)))}" if c else (cc or None)
    ranked = _dash_top_counts(_cc_label, 10)
    msg = "🌍 <b>Negara Paling Banyak OTP</b>\n\n" + _dash_bar_chart(ranked)
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_countries", style="primary")]))

async def cb_dash_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    def _svc_label(l):
        sid = l.get("service", "")
        s   = services.get(sid)
        return f"{get_svc_icon_html(sid)} {html.escape(str(s.get('name', sid)))}" if s else (sid or None)
    ranked = _dash_top_counts(_svc_label, 10)
    msg = "📱 <b>Aplikasi Paling Sering Digunakan</b>\n\n" + _dash_bar_chart(ranked)
    await safe_edit(query, msg[:4000], parse_mode="HTML", reply_markup=_dash_back_kb(
        [mkbtn("admin_refresh", "Refresh", callback_data="dash_apps", style="primary")]))

async def cb_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    sess = get_session(uid)
    sess["state"] = "admin_broadcast"
    await query.edit_message_text(
        "📢 <b>Broadcast Message</b>\n\nSend the message to broadcast to all users:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    commission = settings.get("referralCommission", 10)
    scope      = get_otp_search_scope()
    show_count = settings.get("showCountOnCountryBtn", True)
    cek_bio_url   = settings.get("cek_bio_wa_url", "-")
    fix_merah_url = settings.get("fix_merah_url", "-")
    hidden_mask    = settings.get("hidden_number_mask", "••••")
    hidden_mask_id = settings.get("hidden_number_mask_id")
    pfx           = int(settings.get("mask_prefix_digits", 4))
    sfx           = int(settings.get("mask_suffix_digits", 2))
    sample        = f"628123456789"
    # emoji_html() supaya mask Custom Emoji Premium tampil dengan desain asli
    # (tag <tg-emoji>), bukan karakter fallback bintang/sparkle.
    hidden_mask_html = emoji_html({"char": hidden_mask, "id": hidden_mask_id})
    mask_preview_html = html.escape(sample[:pfx]) + hidden_mask_html + html.escape(sample[-sfx:] if sfx > 0 else "")
    ad_on         = settings.get("autoDeleteOtpEnabled", False)
    ad_min        = settings.get("autoDeleteOtpMinutes", 5)
    await query.edit_message_text(
        f"⚙️ <b>Bot Settings</b>\n\n"
        f"📞 Number Count: <b>{settings['defaultNumberCount']}</b>\n"
        f"⏱ Cooldown: <b>{settings['cooldownSeconds']} seconds</b>\n"
        f"🔐 Verification: <b>{'Enabled ✅' if settings['requireVerification'] else 'Disabled ❌'}</b>\n"
        f"💵 OTP Price: <b>{settings.get('defaultOtpPrice', 0.25):.2f} USD</b>\n"
        f"🔍 OTP Search Window: <b>{settings.get('otpSearchWindowMinutes', 5)} minutes</b>\n"
        f"📍 OTP Search Scope: <b>{OTP_SCOPE_LABELS.get(scope, scope)}</b>\n"
        f"💸 Min Withdraw: <b>{settings['minWithdraw']} USD</b>\n"
        f"🏧 Withdraw: <b>{'Enabled ✅' if settings['withdrawEnabled'] else 'Disabled ❌'}</b>\n"
        f"👥 Referral Commission: <b>{commission}%</b>\n"
        f"📢 Stock Notify Users: <b>{'Enabled ✅' if settings.get('stockNotifyUsers', False) else 'Disabled ❌'}</b>\n"
        f"🔢 Show Count on Country Btn: <b>{'ON ✅' if show_count else 'OFF ❌'}</b>\n"
        f"🔵 Cek Bio WA URL: `{cek_bio_url}`\n"
        f"🔴 FIX Merah URL: `{fix_merah_url}`\n"
        f"🙈 Hidden Mask: `{hidden_mask_html}` | Depan: *{pfx}<b> | Belakang: </b>{sfx}*\n"
        f"   Preview: `{mask_preview_html}`\n"
        f"🗑 Auto-Delete OTP Grup: <b>{'ON ✅ (' + str(ad_min) + ' menit)' if ad_on else 'OFF ❌'}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_count", "Number Count", callback_data="as_count", style="success"),
             mkbtn("a_cooldown", "Cooldown", callback_data="as_cooldown", style="success")],
            [mkbtn("a_settings", f"🔐 Verification {'🔴 Disable' if settings['requireVerification'] else '🟢 Enable'}", callback_data="as_toggle_verify", style="success", auto_icon=False)],
            [mkbtn("a_otp_price", "OTP Price", callback_data="as_price", style="success"),
             mkbtn("a_min_withdraw", "Min Withdraw", callback_data="as_minw", style="danger")],
            [mkbtn("a_otp_window", "OTP Search Window", callback_data="as_otpwindow", style="success")],
            [mkbtn("a_settings", f"📍 OTP Scope: {OTP_SCOPE_LABELS.get(scope, scope)}", callback_data="as_otpscope", style="success", auto_icon=False)],
            [mkbtn("a_withdrawals", f"🏧 Withdraw {'🔴 Disable' if settings['withdrawEnabled'] else '🟢 Enable'}", callback_data="as_toggle_withdraw", style="danger", auto_icon=False)],
            [mkbtn("a_referral_st", f"👥 Referral Commission ({commission}%)", callback_data="as_referral_commission", style="success", auto_icon=False)],
            [InlineKeyboardButton(f"📢 Stock Notify: {'🔴 Disable' if settings.get('stockNotifyUsers', False) else '🟢 Enable'}", callback_data="as_toggle_stocknotify", api_kwargs=_make_btn_kwargs("danger" if settings.get("stockNotifyUsers", False) else "success", get_btn_emoji_id("a_broadcast", "📢")))],
            [InlineKeyboardButton(f"🔢 Show Count: {'🔴 Hide' if show_count else '🟢 Show'}", callback_data="as_toggle_countbtn", api_kwargs=_make_btn_kwargs("danger" if show_count else "success", get_btn_emoji_id("a_settings", "⚙️")))],
            [mkbtn("a_hm_manual", f"🙈 Hidden Mask: {'✨ Premium' if hidden_mask_id else hidden_mask}", callback_data="as_set_hidden_mask", style="primary", auto_icon=False)],
            [mkbtn("a_cek_bio_url", "Set Cek Bio WA URL", callback_data="as_set_cek_bio_url", style="primary"),
             mkbtn("a_fix_merah_url", "Set FIX Merah URL", callback_data="as_set_fix_merah_url", style="danger")],
            [mkbtn("a_settings", "🗑 Auto-Delete OTP Grup", callback_data="as_autodelete", style="primary", auto_icon=False)],
            [mkbtn("a_settings", "Feature On/Off", callback_data="admin_features", style="success")],
            [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
        ])
    )

async def cb_admin_toggle_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["requireVerification"] = not settings["requireVerification"]
    save_settings()
    await query.answer(f"✅ Verification {'Enabled' if settings['requireVerification'] else 'Disabled'}")
    await cb_admin_settings(update, context)

async def cb_admin_toggle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["withdrawEnabled"] = not settings["withdrawEnabled"]
    save_settings()
    await query.answer(f"✅ Withdraw {'Enabled' if settings['withdrawEnabled'] else 'Disabled'}")
    await cb_admin_settings(update, context)

async def cb_admin_toggle_stocknotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["stockNotifyUsers"] = not settings.get("stockNotifyUsers", False)
    save_settings()
    await query.answer(f"✅ Stock Notify {'Enabled' if settings['stockNotifyUsers'] else 'Disabled'}")
    await cb_admin_settings(update, context)

async def cb_admin_toggle_countbtn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["showCountOnCountryBtn"] = not settings.get("showCountOnCountryBtn", True)
    save_settings()
    status = "ON ✅" if settings["showCountOnCountryBtn"] else "OFF ❌"
    await query.answer(f"✅ Show Count on Country Btn: {status}")
    await cb_admin_settings(update, context)

# ─── Language Switch ───
async def cb_lang_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    # Show language selection
    await query.edit_message_text(
        t(uid, "lang_select_title"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_settings", "🇺🇸 English", callback_data="set_lang:en", style="success", auto_icon=False)],
            [mkbtn("a_settings", "🇮🇩 Indonesia", callback_data="set_lang:id", style="success", auto_icon=False)],
            [mkbtn("back", "Back", callback_data="back_to_profile", style="primary")],
        ])
    )

async def cb_set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    uid    = str(update.effective_user.id)
    lang   = query.data.split(":", 1)[1]
    if lang not in ("en", "id"):
        return await query.answer("❌ Unknown language")
    if uid not in users:
        users[uid] = {}
    users[uid]["language"] = lang
    await async_save_users()
    await query.answer()
    msg_key = "lang_set_en" if lang == "en" else "lang_set_id"
    await query.edit_message_text(t_html(uid, msg_key), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            mkbtn("back", "Back to Profile", callback_data="back_to_profile", style="primary")
        ]])
    )

async def cb_back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_profil(update, context)

# ─── Fitur On/Off (semua fitur bisa dinyalakan/dimatikan admin) ───
async def cb_admin_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    lines = []
    rows  = []
    for key, label in FEATURE_LIST:
        on = is_feature_enabled(key)
        lines.append(f"{'✅' if on else '❌'} {label}")
        rows.append([InlineKeyboardButton(
            f"{label} — {'🔴 Matikan' if on else '🟢 Nyalakan'}",
            callback_data=f"feat_toggle:{key}",
            api_kwargs=_make_btn_kwargs("danger" if on else "success", get_btn_emoji_id("a_settings", "⚙️"))
        )])
    rows.append([mkbtn("admin_back", "Back", callback_data="admin_settings", style="primary")])

    await query.edit_message_text(
        "🔌 <b>Fitur On/Off</b>\n\n"
        "Status fitur saat ini:\n" + "\n".join(lines) +
        "\n\nTap tombol di bawah untuk nyalakan/matikan:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_feat_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    key = query.data.split(":", 1)[1]
    valid_keys = {k for k, _ in FEATURE_LIST}
    if key not in valid_keys:
        return await query.answer("❌ Fitur tidak dikenal", show_alert=True)
    new_val = not is_feature_enabled(key)
    set_feature_enabled(key, new_val)
    label = dict(FEATURE_LIST)[key]
    await query.answer(f"✅ {label} {'diaktifkan' if new_val else 'dinonaktifkan'}")
    await cb_admin_features(update, context)

async def cb_as_referral_commission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_referral_commission"
    current = settings.get("referralCommission", 10)
    await query.edit_message_text(
        f"👥 <b>Set Referral Commission</b>\n\n"
        f"Current: <b>{current}%</b>\n\n"
        f"Send new commission percentage (0-50):\n"
        f"Example: <code>10</code> means 10%",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_set_cek_bio_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: set URL untuk tombol Cek Bio WA di menu Tools."""
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_cek_bio_url"
    current = settings.get("cek_bio_wa_url", "-")
    await query.edit_message_text(
        f"🔵 <b>Set URL — Cek Bio WA</b>\n\n"
        f"URL ini digunakan oleh tombol <b>Cek Bio WA</b> di menu Tools.\n\n"
        f"Current: `{current}`\n\n"
        f"Kirim URL baru (contoh: <code>https://t.me/yourbotname</code>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_set_fix_merah_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: set URL untuk tombol FIX Merah di menu Tools."""
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_fix_merah_url"
    current = settings.get("fix_merah_url", "-")
    await query.edit_message_text(
        f"🔴 <b>Set URL — FIX Merah</b>\n\n"
        f"URL ini digunakan oleh tombol <b>FIX Merah</b> di menu Tools.\n\n"
        f"Current: `{current}`\n\n"
        f"Kirim URL baru (contoh: <code>https://t.me/yourbotname</code>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

def _hidden_number_panel_text() -> str:
    mask   = settings.get("hidden_number_mask", "••••")
    mid    = settings.get("hidden_number_mask_id")
    pfx    = int(settings.get("mask_prefix_digits", 4))
    sfx    = int(settings.get("mask_suffix_digits", 2))
    sample = "628123456789"
    front  = sample[:pfx]
    back   = sample[-sfx:] if sfx > 0 else ""
    # Render mask via emoji_html() supaya kalau mask-nya Custom Emoji Premium
    # (punya custom_emoji_id), yang tampil adalah desain emoji ASLI lewat tag
    # <tg-emoji> — bukan cuma karakter fallback (biasanya muncul sebagai ⭐/✨)
    # seperti sebelumnya waktu ditampilkan sebagai teks polos di dalam backtick.
    mask_html = emoji_html({"char": mask, "id": mid})
    prev_html = html.escape(front) + mask_html + html.escape(back)
    premium_line = f"\n✨ <b>Custom Emoji ID:</b>  <code>{html.escape(str(mid))}</code>" if mid else ""
    return (
        f"🙈 <b>Hidden Number Settings</b>\n\n"
        f"Atur berapa digit depan & belakang yang terlihat, serta teks/emoji mask di tengah.\n"
        f"Mask juga bisa diisi Custom Emoji Premium via ID (tombol \"Ketik Mask Manual\").\n\n"
        f"──────────────────────\n"
        f"🔢 <b>Digit Depan (Prefix):</b>  `{pfx}`\n"
        f"🔢 <b>Digit Belakang (Suffix):</b> `{sfx}`\n"
        f"🎭 <b>Mask Tengah:</b>  `{mask_html}`{premium_line}\n"
        f"──────────────────────\n"
        f"👁 <b>Preview:</b>  `{prev_html}`\n"
        f"──────────────────────"
    )

def _hidden_number_panel_kb() -> InlineKeyboardMarkup:
    pfx = int(settings.get("mask_prefix_digits", 4))
    sfx = int(settings.get("mask_suffix_digits", 2))
    return InlineKeyboardMarkup([
        # ── Prefix row ──
        [
            InlineKeyboardButton(f"◀ Depan: {pfx}", callback_data="hmd:pfx:-1", api_kwargs=_make_btn_kwargs("primary", get_btn_emoji_id("a_hm_manual", "✏️"))),
            InlineKeyboardButton(f"▶ Depan: {pfx}", callback_data="hmd:pfx:+1", api_kwargs=_make_btn_kwargs("primary", get_btn_emoji_id("a_hm_manual", "✏️"))),
        ],
        # ── Suffix row ──
        [
            InlineKeyboardButton(f"◀ Belakang: {sfx}", callback_data="hmd:sfx:-1", api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("a_hm_manual", "✏️"))),
            InlineKeyboardButton(f"▶ Belakang: {sfx}", callback_data="hmd:sfx:+1", api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("a_hm_manual", "✏️"))),
        ],
        # ── Mask preset row ──
        [
            InlineKeyboardButton("••••", callback_data="hm:••••", api_kwargs=_make_btn_kwargs("primary", get_btn_emoji_id("a_hm_manual", "✏️"))),
            InlineKeyboardButton("****", callback_data="hm:****", api_kwargs=_make_btn_kwargs("primary", get_btn_emoji_id("a_hm_manual", "✏️"))),
            InlineKeyboardButton("----", callback_data="hm:----", api_kwargs=_make_btn_kwargs("primary", get_btn_emoji_id("a_hm_manual", "✏️"))),
        ],
        [
            InlineKeyboardButton("🔒", callback_data="hm:🔒", api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("a_hm_manual", "✏️"))),
            InlineKeyboardButton("🙈", callback_data="hm:🙈", api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("a_hm_manual", "✏️"))),
            InlineKeyboardButton("▓▓▓", callback_data="hm:▓▓▓", api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("a_hm_manual", "✏️"))),
        ],
        [mkbtn("a_hm_manual", "Ketik Mask Manual", callback_data="hm:__manual__", style="primary")],
        [mkbtn("admin_back", "Kembali", callback_data="admin_settings", style="primary")],
    ])

async def cb_as_set_hidden_mask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: panel lengkap hidden number — mask, prefix, suffix."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        _hidden_number_panel_text(),
        parse_mode="HTML",
        reply_markup=_hidden_number_panel_kb()
    )

async def cb_hidden_mask_digit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naikkan/turunkan digit prefix/suffix pakai tombol +/-."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    _, field, delta_str = query.data.split(":")   # hmd:pfx:+1 / hmd:sfx:-1
    delta = int(delta_str)
    key   = "mask_prefix_digits" if field == "pfx" else "mask_suffix_digits"
    cur   = int(settings.get(key, 4 if field == "pfx" else 2))
    new   = max(0, min(10, cur + delta))
    if new == cur:
        return await query.answer("Batas minimum/maksimum (0–10)", show_alert=True)
    settings[key] = new
    save_settings()
    await query.answer(f"✅ {'Depan' if field == 'pfx' else 'Belakang'}: {new} digit")
    await query.edit_message_text(
        _hidden_number_panel_text(),
        parse_mode="HTML",
        reply_markup=_hidden_number_panel_kb()
    )

async def cb_hidden_mask_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pilih preset mask atau buka input manual."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    value = query.data.split(":", 1)[1]
    if value == "__manual__":
        await query.answer()
        get_session(uid)["state"] = "admin_set_hidden_mask"
        current    = settings.get("hidden_number_mask", "••••")
        current_id = settings.get("hidden_number_mask_id")
        current_html = emoji_html({"char": current, "id": current_id})
        await query.edit_message_text(
            f"✏️ <b>Ketik Mask Baru</b>\n\n"
            f"Mask saat ini: `{current_html}`\n\n"
            f"Kirim salah satu:\n"
            f"• Teks/emoji biasa (maks 20 karakter)\n"
            f"• Tempel Custom Emoji Telegram Premium\n"
            f"• ID emoji langsung (angka, mis. <code>5368324170671202286</code>)",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                mkbtn("a_confirm_no", "Cancel", callback_data="as_set_hidden_mask", style="danger")
            ]])
        )
    else:
        settings["hidden_number_mask"]    = value
        settings["hidden_number_mask_id"] = None   # preset = teks/emoji biasa, bukan Premium
        save_settings()
        await query.answer(f"✅ Mask: {value}")
        await query.edit_message_text(
            _hidden_number_panel_text(),
            parse_mode="HTML",
            reply_markup=_hidden_number_panel_kb()
        )

async def cb_admin_referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    commission = settings.get("referralCommission", 10)
    total_referrals = sum(u.get("referralCount", 0) for u in users.values())
    total_ref_earn  = sum(e.get("referralEarnings", 0) for e in earnings.values())

    msg = (
        f"👥 <b>Referral System Stats</b>\n\n"
        f"📌 Commission Rate: <b>{commission}%</b>\n"
        f"👥 Total Referrals: <b>{total_referrals}</b>\n"
        f"💰 Total Commission Paid: <b>{total_ref_earn:.2f} USD</b>\n\n"
        f"🏆 <b>Top Referrers:</b>\n"
    )

    top_ref = sorted(
        [(uid_k, u.get("referralCount", 0)) for uid_k, u in users.items()],
        key=lambda x: x[1], reverse=True
    )[:10]

    for r_uid, r_count in top_ref:
        if r_count == 0:
            continue
        r_user = users.get(r_uid, {})
        r_name = r_user.get("first_name", "User").replace("*", "").replace("_", "")
        r_earn = earnings.get(r_uid, {}).get("referralEarnings", 0)
        msg += f"  👤 {r_name} | {r_count} referrals | {r_earn:.2f} USD\n"

    if len(msg) > 4000:
        msg = msg[:3950] + "\n...<i>truncated</i>"

    await query.edit_message_text(
        msg, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_referral_st", f"⚙️ Set Commission ({commission}%)", callback_data="as_referral_commission", style="success", auto_icon=False)],
            [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
        ])
    )

async def cb_as_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_count"
    await query.edit_message_text(
        f"📞 <b>Set Number Count</b>\n\nCurrent: *{settings['defaultNumberCount']}*\n\nSend new count (1-100):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_cooldown"
    await query.edit_message_text(
        f"⏱ <b>Set Cooldown</b>\n\nCurrent: *{settings['cooldownSeconds']} seconds*\n\nSend new cooldown (1-3600):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_price"
    await query.edit_message_text(
        f"💵 <b>Set Default OTP Price</b>\n\nCurrent: *{settings.get('defaultOtpPrice', 0.25):.2f} USD*\n\nSend new price:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_minw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_minw"
    await query.edit_message_text(
        f"💸 <b>Set Min Withdraw</b>\n\nCurrent: *{settings['minWithdraw']} USD*\n\nSend new minimum:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_otpwindow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_otpwindow"
    await query.edit_message_text(
        f"🔍 <b>Set Cari OTP Window</b>\n\n"
        f"Current: <b>{settings.get('otpSearchWindowMinutes', 5)} menit</b>\n\n"
        f"User hanya bisa melihat OTP yang masuk dalam rentang waktu ini.\n\n"
        f"Send new window in menit (1-1440):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_as_otpscope(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    new_scope = cycle_otp_scope()
    await query.answer(f"📍 Cari OTP diatur ke: {OTP_SCOPE_LABELS.get(new_scope, new_scope)}")
    await cb_admin_settings(update, context)

def _autodelete_panel_text() -> str:
    on  = settings.get("autoDeleteOtpEnabled", False)
    mnt = settings.get("autoDeleteOtpMinutes", 5)
    return (
        f"🗑 <b>Auto-Delete OTP Grup</b>\n\n"
        f"Kalau di-ON, setiap pesan OTP yang masuk ke Grup OTP (baik yang bot "
        f"kirim sendiri lewat panel, maupun pesan mentah yang diteruskan dari "
        f"akun WA/SMS) akan otomatis dihapus dari grup setelah durasi yang "
        f"diatur di bawah. Pesan DM ke user (notifikasi OTP pribadi) TIDAK "
        f"ikut terhapus.\n\n"
        f"──────────────────────\n"
        f"Status : <b>{'ON ✅' if on else 'OFF ❌'}</b>\n"
        f"Durasi : <b>{mnt} menit</b>\n"
        f"──────────────────────"
    )

def _autodelete_panel_kb() -> InlineKeyboardMarkup:
    on = settings.get("autoDeleteOtpEnabled", False)
    return InlineKeyboardMarkup([
        [mkbtn("a_settings", f"{'🔴 Matikan' if on else '🟢 Nyalakan'} Auto-Delete", callback_data="as_toggle_autodelete", style=("danger" if on else "success"))],
        [InlineKeyboardButton("◀ 1 menit",  callback_data="ad_preset:1"),
         InlineKeyboardButton("5 menit",    callback_data="ad_preset:5"),
         InlineKeyboardButton("10 menit ▶", callback_data="ad_preset:10")],
        [InlineKeyboardButton("15 menit", callback_data="ad_preset:15"),
         InlineKeyboardButton("30 menit", callback_data="ad_preset:30"),
         InlineKeyboardButton("60 menit", callback_data="ad_preset:60")],
        [mkbtn("a_hm_manual", "Ketik Durasi Manual", callback_data="ad_preset:__manual__", style="primary")],
        [mkbtn("admin_back", "Kembali", callback_data="admin_settings", style="primary")],
    ])

async def cb_as_autodelete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: panel Auto-Delete OTP Grup — toggle on/off & atur durasi (menit)."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        _autodelete_panel_text(),
        parse_mode="HTML",
        reply_markup=_autodelete_panel_kb()
    )

async def cb_as_toggle_autodelete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    settings["autoDeleteOtpEnabled"] = not settings.get("autoDeleteOtpEnabled", False)
    save_settings()
    on = settings["autoDeleteOtpEnabled"]
    await query.answer(f"✅ Auto-Delete OTP Grup: {'ON' if on else 'OFF'}")
    await query.edit_message_text(
        _autodelete_panel_text(),
        parse_mode="HTML",
        reply_markup=_autodelete_panel_kb()
    )

async def cb_autodelete_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pilih durasi preset (menit) atau buka input manual."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    value = query.data.split(":", 1)[1]
    if value == "__manual__":
        await query.answer()
        get_session(uid)["state"] = "admin_set_autodelete_minutes"
        current = settings.get("autoDeleteOtpMinutes", 5)
        await query.edit_message_text(
            f"✏️ <b>Ketik Durasi Auto-Delete</b>\n\n"
            f"Durasi saat ini: <b>{current} menit</b>\n\n"
            f"Kirim jumlah menit (angka, 1–10080, mis. <code>10</code>):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                mkbtn("a_confirm_no", "Cancel", callback_data="as_autodelete", style="danger")
            ]])
        )
        return
    try:
        minutes = int(value)
    except ValueError:
        return await query.answer("❌ Nilai tidak valid", show_alert=True)
    settings["autoDeleteOtpMinutes"] = max(1, minutes)
    save_settings()
    await query.answer(f"✅ Durasi Auto-Delete: {minutes} menit")
    await query.edit_message_text(
        _autodelete_panel_text(),
        parse_mode="HTML",
        reply_markup=_autodelete_panel_kb()
    )

async def cb_admin_add_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_add_numbers"
    await query.edit_message_text(
        "➕ <b>Add Numbers</b>\n\nFormat:\n<code>[number]|[country code]|[service]</code>\n\nExample:\n<code>8801712345678|880|whatsapp</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    pending = [w for w in withdrawals if w["status"] == "pending"]
    msg = f"💸 <b>Pending Withdrawals:</b> {len(pending)}\n\n"

    for w in pending[:10]:
        msg += f"🆔 `{w['id'][-8:]}`\n"
        msg += f"👤 {w.get('userName','')} | 💵 {w['amount']:.2f} USD\n"
        msg += f"📱 {w['method']}: `{w['account']}`\n\n"

    buttons = []
    for w in pending[:5]:
        buttons.append([
            mkbtn("a_confirm_yes", f"✅ {w['id'][-6:]}", callback_data=f"wadm_approve:{w['id']}", style="success", auto_icon=False),
            mkbtn("a_confirm_no", f"❌ {w['id'][-6:]}", callback_data=f"wadm_reject:{w['id']}", style="danger", auto_icon=False),
        ])
    buttons.append([mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")])

    await query.edit_message_text(msg[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cb_withdraw_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    wid = query.data.split(":", 1)[1]
    for w in withdrawals:
        if w["id"] == wid:
            # BUG FIX: sebelumnya tidak ada pengecekan status. Kalau tombol
            # ini di-klik dua kali (double-tap admin, atau klik dari pesan
            # lama yang belum ter-refresh), withdrawal yang sama bisa
            # diproses berulang kali. Untuk approve ini terutama berbahaya
            # kalau kombinasi dengan reject: withdrawal yang sudah di-approve
            # (dan sudah dibayar manual di luar bot) lalu di-reject bisa
            # bikin saldo user di-refund padahal uangnya sudah keluar.
            if w["status"] != "pending":
                await query.answer(f"⚠️ Withdrawal ini sudah diproses ({w['status']}).", show_alert=True)
                return await cb_admin_withdrawals(update, context)
            w["status"] = "approved"
            w["processedAt"] = now_wib().isoformat()
            await async_save_withdrawals()
            await query.answer("✅ Approved!")
            try:
                await context.bot.send_message(w["userId"],
                    f"✅ <b>Withdrawal Approved!</b>\n\n💵 {w['amount']:.2f} USD → {html.escape(w['method'])}: <code>{html.escape(w['account'])}</code>",
                    parse_mode="HTML")
            except:
                pass
            break
    await cb_admin_withdrawals(update, context)

async def cb_withdraw_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    wid = query.data.split(":", 1)[1]
    for w in withdrawals:
        if w["id"] == wid:
            # BUG FIX: sama seperti approve — cegah reject dobel (yang bisa
            # menyebabkan refund saldo dobel ke user).
            if w["status"] != "pending":
                await query.answer(f"⚠️ Withdrawal ini sudah diproses ({w['status']}).", show_alert=True)
                return await cb_admin_withdrawals(update, context)
            w["status"] = "rejected"
            w["processedAt"] = now_wib().isoformat()
            e = get_user_earnings(w["userId"])
            e["balance"] = round(e["balance"] + w["amount"], 2)
            await async_save_earnings()
            await async_save_withdrawals()
            await query.answer("❌ Rejected!")
            try:
                await context.bot.send_message(w["userId"],
                    f"❌ <b>Withdrawal Rejected.</b>\n\n💵 {w['amount']:.2f} USD refunded.",
                    parse_mode="HTML")
            except:
                pass
            break
    await cb_admin_withdrawals(update, context)

async def cb_admin_balance_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        "👛 <b>Balance Management</b>\n\nSelect action:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_bal_add", "Add Balance", callback_data="bal_add", style="success"),
             mkbtn("a_bal_deduct", "Deduct Balance", callback_data="bal_deduct", style="success")],
            [mkbtn("a_bal_reset", "Reset Balance", callback_data="bal_reset", style="primary")],
            [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
        ])
    )

async def cb_bal_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_add_balance"
    await query.edit_message_text(
        "➕ <b>Add Balance</b>\n\nFormat: <code>[userId] [amount]</code>\nExample: <code>123456789 50</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_bal_deduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_deduct_balance"
    await query.edit_message_text(
        "➖ <b>Deduct Balance</b>\n\nFormat: <code>[userId] [amount]</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_bal_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_reset_balance"
    await query.edit_message_text(
        "🔄 <b>Reset Balance</b>\n\nSend the userId:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_admin_country_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = "admin_set_country_price"
    text = "💰 <b>Country Prices</b>\n\nCurrent prices:\n"
    for cc, c in countries.items():
        p = country_prices.get(cc, settings.get("defaultOtpPrice", 0.25))
        text += f"{c['flag']} +{cc}: <b>{p:.2f} USD</b>\n"
    text += "\nSend new prices (format: <code>880 0.50</code>):"

    await query.edit_message_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]]))

async def cb_admin_manage_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        f"🌍 <b>Manage Countries</b>\n\nTotal: *{len(countries)}*",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_add_numbers", "Add Country", callback_data="country_add", style="success"),
             mkbtn("a_cntry_list", "List Countries", callback_data="country_list", style="primary")],
            [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
        ])
    )

async def cb_country_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🌍 <b>Country List</b>\n\n"
    for cc, c in countries.items():
        p = country_prices.get(cc, settings.get("defaultOtpPrice", 0.25))
        text += f"{c['flag']} <b>{c['name']}</b> (+{cc}) — {p:.2f} USD/OTP\n"
    await query.edit_message_text(text[:4000], parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("admin_back", "Back", callback_data="admin_manage_countries", style="primary")]]))

async def cb_country_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_add_country"
    await query.edit_message_text(
        "🌍 <b>Add Country</b>\n\nFormat: <code>[code] [name] [flag]</code>\nExample: <code>880 Bangladesh 🇧🇩</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_admin_manage_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    await query.edit_message_text(
        "🔧 <b>Manage Services</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_cntry_list", "List Services", callback_data="svc_list", style="primary"),
             mkbtn("a_add_numbers", "Add Service", callback_data="svc_add", style="success")],
            [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
        ])
    )

async def cb_svc_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📋 <b>Services List</b>\n\n"
    for svc_id, svc in services.items():
        text += f"• {get_svc_icon_html(svc_id)} <b>{html.escape(str(svc.get('name','-')))}</b> (ID: <code>{html.escape(svc_id)}</code>)\n"
    await safe_edit(query, text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("admin_back", "Back", callback_data="admin_manage_services", style="primary")]]))

async def cb_svc_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_add_service"
    await query.edit_message_text(
        "🔧 <b>Add Service</b>\n\nFormat: <code>[id] [name] [icon]</code>\nExample: <code>facebook Facebook 📘</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    sess = get_session(uid)
    sess["state"] = "admin_upload_select_service"

    buttons = [[mkbtn("a_upload", f"{svc['name']}", callback_data=f"upload_svc:{svc_id}", style="success")]
               for svc_id, svc in services.items()]
    buttons.append([mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")])
    await query.edit_message_text("📤 <b>Upload Numbers</b>\n\nSelect service:", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_upload_svc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    svc_id = query.data.split(":", 1)[1]
    svc    = services.get(svc_id, {"name": svc_id})
    sess   = get_session(uid)
    sess["state"] = "admin_upload_file"
    sess["data"]  = {"serviceId": svc_id}
    await query.edit_message_text(
        f"📤 <b>Upload Numbers for {svc['name']}</b>\n\nSend a .txt file with numbers (one per line).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_confirm_no", "Cancel", callback_data="admin_cancel", style="danger")]])
    )

async def cb_admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("🛠 <b>Admin Dashboard</b>\n\nSelect an option:", parse_mode="HTML", reply_markup=admin_keyboard())

async def cb_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("❌ <b>Cancelled.</b>", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("a_admin_pnl", "Back to Admin", callback_data="admin_back", style="primary")]]))

# ─── Custom Emoji Admin Panel (DIBANGUN ULANG — backend: SQLite) ───────────
# - Kategori "Service / Negara / Tombol / Lainnya": tetap edit massal via teks
#   (`key= emoji` per baris) — cocok untuk banyak entri sekaligus.
# - Kategori "Template OTP" & "Premium": edit PER-SLOT, satu emoji per pesan.
#   Ini penting supaya bot bisa menangkap custom_emoji_id ASLI kalau admin/​
#   user Premium MENEMPEL Custom Emoji Telegram (bukan sekadar unicode biasa).
#   Emoji yang tersimpan lengkap dengan ID-nya dirender pakai tag <tg-emoji>,
#   sehingga SEMUA user (gratis maupun premium) tetap bisa MELIHAT desain
#   aslinya — hanya menempelnya saja yang butuh Telegram Premium.

BULK_EMOJI_CATS = ("service", "country", "button", "other")
SLOT_EMOJI_CATS = ("template", "premium")

# Dasar dari daftar tombol menu bawah (MAIN_MENU_BUTTON_SPECS) supaya default
# di sini SELALU sinkron dengan default yang dipakai di menu bawah asli —
# ditambah slot lain (verify/back/cancel/notify) yang dipakai di tempat lain.
_BUTTON_EMOJI_DEFAULTS = {spec[1]: spec[2] for spec in MAIN_MENU_BUTTON_SPECS}
_BUTTON_EMOJI_DEFAULTS.update({
      # ─── System / Navigation ───────────────────────────────────────────────
      "verify":          "✅",
      "back":            "🔙",
      "cancel":          "❌",
      "refresh":         "🔄",
      "home":            "🏠",
      "notify":          "🎉",
      # ─── Numbers ────────────────────────────────────────────────────────────
      "copy_all":        "📋",
      "open_otp_group":  "📨",
      "get_new_numbers": "🔄",
      "service_list":    "🔙",
      # ─── Get File ────────────────────────────────────────────────────────────
      "file_open_otp":   "📨",
      "file_redownload": "🔄",
      "file_pick_cntry": "🌍",
      "file_svc_list":   "🏠",
      # ─── Profile / Balance ───────────────────────────────────────────────────
      "balance_btn":     "💰",
      "withdraw_btn":    "💸",
      "referral_btn":    "👥",
      "withdraw_hist":   "📋",
      "start_withdraw":  "💸",
      "share_link":      "🔗",
      "ref_stats":       "📊",
      "view_prem_emoji": "👑",
      "lang_switch":     "🌐",
      # ─── Withdraw ────────────────────────────────────────────────────────────
      "wm_bkash":        "🟣",
      "wm_nagad":        "🟠",
      "w_cancel":        "❌",
      # ─── Tools ───────────────────────────────────────────────────────────────
      "tempmail":        "📧",
      "twofa":           "🔐",
      "cek_bio_wa":      "🔵",
      "fix_merah":       "🔴",
      # ─── TempMail ────────────────────────────────────────────────────────────
      "tm_check_inbox":  "📬",
      "tm_show":         "📋",
      "tm_new_email":    "🔄",
      "tm_delete":       "🗑️",
      "tm_create":       "🆕",
      "tm_retry":        "🔄",
      # ─── 2FA ─────────────────────────────────────────────────────────────────
      "totp_facebook":   "📘",
      "totp_instagram":  "📸",
      "totp_google":     "🔍",
      "totp_other":      "⚙️",
      "totp_refresh":    "🔄",
      "totp_back":       "🔙",
      "totp_cancel":     "❌",
      # ─── OTP Search ──────────────────────────────────────────────────────────
      "otp_search_again":"🔄",
      "otp_cancel":      "❌",
      # ─── WhatsApp ────────────────────────────────────────────────────────────
      "wa_connect":      "📱",
      "wa_disconnect":   "🔴",
      "wa_status":       "📊",
      # ─── Verification ────────────────────────────────────────────────────────
      "verify_btn":      "✅",
      "main_ch":         "1️⃣",
      "num_ch":          "2️⃣",
      "otp_grp":         "3️⃣",
      # ─── Live Traffic ────────────────────────────────────────────────────────
      "live_refresh":    "🔄",
      "live_stock":      "📊",
      # ─── Support ─────────────────────────────────────────────────────────────
      "contact_admin":   "💬",
      # ─── Admin Panel ─────────────────────────────────────────────────────────
      "admin_back":      "🔙",
      "admin_refresh":   "🔄",
      "a_user_stats":    "👥",
      "a_live_traffic":  "🔥",
      "a_otp_log":       "📋",
      "a_live_timeline": "📡",
      "a_dashboard":     "📈",
      "a_broadcast":     "📢",
      "a_add_numbers":   "➕",
      "a_upload":        "📤",
      "a_delete":        "🗑️",
      "a_manage_svc":    "🔧",
      "a_manage_cntry":  "🌍",
      "a_settings":      "⚙️",
      "a_prices":        "💰",
      "a_withdrawals":   "💸",
      "a_balance_mgmt":  "👛",
      "a_referral_st":   "👥",
      "a_otp_panels":    "📡",
      "a_global_wa":     "📱",
      "a_custom_emoji":  "🎨",
      "a_logout":        "🚪",
      "a_count":         "📞",
      "a_cooldown":      "⏱",
      "a_otp_price":     "💵",
      "a_min_withdraw":  "💸",
      "a_otp_window":    "🔍",
      "a_cek_bio_url":   "🔵",
      "a_fix_merah_url": "🔴",
      "a_dash_hourly":   "⏰",
      "a_dash_daily":    "📅",
      "a_dash_monthly":  "🗓️",
      "a_dash_growth":   "📈",
      "a_dash_panels":   "🖥️",
      "a_dash_countries":"🌍",
      "a_dash_apps":     "📱",
      "a_panel_start":   "✅",
      "a_panel_stop":    "⏹",
      "a_panel_restart": "🔄",
      "a_panel_tmpl_g":  "",
      "a_panel_tmpl_u":  "",
      "a_panel_groups":  "👥",
      "a_live_stop":     "⏹️",
      "a_bal_add":       "➕",
      "a_bal_deduct":    "➖",
      "a_bal_reset":     "🔄",
      "a_cntry_list":    "📋",
      "a_emoji_cancel":  "❌",
      "a_hm_manual":     "✏️",
      "a_confirm_yes":   "✅",
      "a_confirm_no":    "❌",
      "a_admin_pnl":     "🛠",
  })
_OTHER_EMOJI_DEFAULTS = {
    "earnings": "💵", "balance": "💰", "otplog": "📨", "country": "🌍",
    "service": "📞", "upload": "📤", "star": "⭐", "new": "🆕",
    "total": "📊", "notify": "🎉",
}
_TEMPLATE_EMOJI_DEFAULTS = {"e1": "\u2705", "e2": "📌", "e3": "📎", "e4": "🔥", "e5": "\u26A1"}
_PREMIUM_EMOJI_DEFAULTS  = {"p1": "👑", "p2": "💎", "p3": "🌟", "p4": "🏆", "p5": "🚀"}

def _template_defaults_dynamic() -> dict:
    """Gabungan slot `e1`..`e5` (fixed) DENGAN slot tambahan yang otomatis
    tersimpan saat admin upload/tempel Template Grup atau Template User yang
    di dalamnya mengandung Custom Emoji Telegram Premium (lihat
    _auto_attach_premium_emoji — slot_key-nya = karakter emoji itu sendiri).
    Supaya emoji hasil upload template JUGA langsung muncul & bisa diedit
    lewat menu 🎨 Custom Emoji → Emoji Template, bukan cuma e1-e5."""
    merged = dict(_TEMPLATE_EMOJI_DEFAULTS)
    for slot_key, entry in (emoji_settings.get("template") or {}).items():
        if slot_key not in merged:
            merged[slot_key] = (entry.get("char") if entry else None) or "✨"
    return merged

def _emoji_custom_keyboard():
    return InlineKeyboardMarkup([
        [mkbtn("a_custom_emoji", "Emoji Service",   callback_data="emoji_cat:service",  style="success"),
         mkbtn("a_manage_cntry", "Emoji Negara",    callback_data="emoji_cat:country",  style="success")],
        [mkbtn("a_settings", "Emoji Tombol",        callback_data="emoji_cat:button",   style="primary"),
         mkbtn("a_custom_emoji", "✨ Emoji Lainnya",  callback_data="emoji_cat:other",  style="primary", auto_icon=False)],
        [mkbtn("a_custom_emoji", "Emoji Template",  callback_data="emoji_cat:template", style="success")],
        [mkbtn("a_confirm_no", "♻️ Reset Semua", callback_data="emoji_reset_all", style="danger", auto_icon=False)],
        [mkbtn("admin_back", "Back",                callback_data="admin_back",         style="primary")],
    ])

def _service_emoji_lines() -> list:
    lines = []
    for svc_id, svc in services.items():
        cur = (emoji_settings.get("service", {}).get(svc_id) or {}).get("char") or svc.get("icon", "📞")
        lines.append(f"{svc['name']}= {cur}")
    return lines

def _country_emoji_lines() -> list:
    lines = []
    for cc, c in countries.items():   # full list — pagination handles Telegram's copy_text limit
        cur = (emoji_settings.get("country", {}).get(cc) or {}).get("char") or c.get("flag", "🌍")
        lines.append(f"{cc}= {cur}")
    return lines

def _button_emoji_lines() -> list:
    lines = []
    for key, default in _BUTTON_EMOJI_DEFAULTS.items():
        cur = (emoji_settings.get("button", {}).get(key) or {}).get("char") or default
        lines.append(f"{key}= {cur}")
    return lines

def _other_emoji_lines() -> list:
    lines = []
    for key, default in _OTHER_EMOJI_DEFAULTS.items():
        cur = (emoji_settings.get("other", {}).get(key) or {}).get("char") or default
        lines.append(f"{key}= {cur}")
    return lines

def _chunk_lines(lines: list, max_chars: int = 230, max_lines: int = 10) -> list:
    """Split lines into pages: dibatasi MAKSIMAL 10 baris per halaman (biar
    daftar panjang seperti negara/tombol tidak bikin loading lama), sekaligus
    tetap dibatasi jumlah karakter supaya tombol 'Salin' (copy_text, limit
    256 karakter dari Telegram) tetap berfungsi."""
    pages, cur, cur_len = [], [], 0
    for ln in lines:
        add = len(ln) + 1
        if cur and (cur_len + add > max_chars or len(cur) >= max_lines):
            pages.append(cur)
            cur, cur_len = [], 0
        cur.append(ln)
        cur_len += add
    if cur:
        pages.append(cur)
    return pages or [[]]

def _build_service_emoji_list() -> str:
    return "\n".join(_service_emoji_lines())

def _build_country_emoji_list() -> str:
    return "\n".join(_country_emoji_lines())

def _build_button_emoji_list() -> str:
    return "\n".join(_button_emoji_lines())

def _build_other_emoji_list() -> str:
    lines = _other_emoji_lines()
    return "\n".join(lines)

def _slot_preview_lines(category: str, defaults: dict) -> list:
    lines = []
    for key, default in defaults.items():
        entry = _emoji_slot(category, key, default)
        tag = " (custom emoji premium ✅)" if entry.get("id") else ""
        lines.append(f"`{key}`: {entry['char']}{tag}")
    return lines

_EMOJI_CAT_INFO = {
    "service": {
        "title": "📱 <b>Emoji Service</b>",
        "desc": (
            "Tiap baris: <code>NamaService= emoji</code> atau <code>NamaService= emoji_id</code>\n"
            "Contoh:\n<code>WhatsApp= 💚</code>\n<code>Telegram= 🔵</code>\n<code>WhatsApp= 5368324170671202286</code>\n\n"
            "💡 <i>Bisa pakai emoji biasa ATAU ID emoji (angka besar — salin dari sticker pack).</i>\n"
            "<i>Gunakan nama service ATAU ID-nya (huruf kecil).</i>\n"
            "<i>Salin list di bawah, edit emoji-nya, lalu kirim balik.</i>"
        ),
        "build_fn": _build_service_emoji_list,
        "lines_fn": _service_emoji_lines,
        "state": "admin_set_emoji_service",
    },
    "country": {
        "title": "🌍 <b>Emoji Negara</b>",
        "desc": (
            "Tiap baris: <code>kode_negara= emoji</code> atau <code>kode_negara= emoji_id</code>\n"
            "Contoh:\n<code>880= 🇧🇩</code>\n<code>62= 🇮🇩</code>\n<code>880= 5368324170671202286</code>\n\n"
            "💡 <i>Bisa pakai emoji biasa ATAU ID emoji (angka besar).</i>\n"
            "<i>Salin list di bawah, edit, lalu kirim balik.</i>"
        ),
        "build_fn": _build_country_emoji_list,
        "lines_fn": _country_emoji_lines,
        "state": "admin_set_emoji_country",
    },
    "button": {
        "title": "🔘 <b>Emoji Tombol</b>",
        "desc": (
            "Tiap baris: <code>key= emoji</code> atau <code>key= emoji_id</code>\n"
            "Contoh:\n<code>get_number= \u260E\uFE0F</code>\n<code>get_file= 📁</code>\n<code>get_number= 5368324170671202286</code>\n\n"
            "💡 <i>Bisa pakai emoji biasa ATAU ID emoji (angka besar).</i>\n"
            "<i>Salin list di bawah, edit, lalu kirim balik.</i>"
        ),
        "build_fn": _build_button_emoji_list,
        "lines_fn": _button_emoji_lines,
        "state": "admin_set_emoji_button",
    },
    "other": {
        "title": "\u2728 <b>Emoji Lainnya</b>",
        "desc": (
            "Tiap baris: <code>key= emoji</code> atau <code>key= emoji_id</code>\n"
            "Contoh:\n<code>notify= 🎊</code>\n<code>balance= 🤑</code>\n<code>notify= 5368324170671202286</code>\n\n"
            "💡 <i>Bisa pakai emoji biasa ATAU ID emoji (angka besar).</i>\n"
            "<i>Salin list di bawah, edit, lalu kirim balik.</i>"
        ),
        "build_fn": _build_other_emoji_list,
        "lines_fn": _other_emoji_lines,
        "state": "admin_set_emoji_other",
    },
}

def _emoji_slot_keyboard(category: str, defaults: dict):
    rows, cur = [], []
    for key in defaults:
        cur.append(mkbtn("a_custom_emoji", key, callback_data=f"emoji_slot:{category}:{key}", style="primary"))
        if len(cur) == 3:
            rows.append(cur); cur = []
    if cur:
        rows.append(cur)
    rows.append([mkbtn("a_emoji_cancel", "Batal", callback_data="emoji_cat_back", style="danger")])
    return InlineKeyboardMarkup(rows)

async def cb_admin_custom_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text(
        "🎨 <b>Custom Emoji</b>\n\n"
        "Pilih kategori emoji yang ingin dikustomisasi.\n"
        "Semua perubahan tersimpan permanen di database dan langsung terlihat oleh semua user.\n\n"
        "⚠️ <b>Syarat wajib dari Telegram (di luar kendali bot ini):</b> emoji Premium "
        "(ID panjang / tempel langsung) HANYA bisa tampil sebagai desain asli kalau akun "
        "Telegram <b>pemilik bot ini</b> (yang bikin bot lewat @BotFather) punya "
        "<b>Telegram Premium aktif</b>, atau bot sudah punya username tambahan dari Fragment.\n"
        "Kalau syarat itu belum terpenuhi, Telegram otomatis menolak dan bot akan fallback "
        "ke emoji biasa/✨ — ini <u>bukan</u> bug, jadi cek dulu status Premium akun owner bot "
        "sebelum lapor emoji tidak tampil.",
        parse_mode="HTML",
        reply_markup=_emoji_custom_keyboard()
    )

async def cb_emoji_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the editable list/slot picker for a given emoji category."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    cat = query.data.split(":", 1)[1]

    if cat in SLOT_EMOJI_CATS:
        defaults = _template_defaults_dynamic() if cat == "template" else _PREMIUM_EMOJI_DEFAULTS
        title = "📝 <b>Emoji Template OTP</b>" if cat == "template" else "👑 <b>Emoji Premium</b>"
        hint = (
            "Gunakan `{e1}<code> s/d </code>{e5}` di template OTP kamu.\n"
            "Emoji yang otomatis terdeteksi dari Template Grup/User yang kamu upload\n"
            "juga langsung muncul sebagai slot di bawah — tinggal tap utk edit.\n"
            if cat == "template" else
            "Emoji ini bisa DILIHAT oleh semua user (free maupun premium) — "
            "TAPI hanya kalau akun <b>pemilik bot ini</b> (owner @BotFather) punya "
            "Telegram Premium aktif (atau bot punya username Fragment). Kalau belum, "
            "Telegram tolak dan otomatis fallback ke emoji biasa/✨.\n"
        )
        preview = "\n".join(_slot_preview_lines(cat, defaults))
        get_session(uid)["state"] = None
        get_session(uid)["data"]  = {"cat": cat}
        await query.edit_message_text(
            f"{title}\n\n{hint}\n"
            "Tap salah satu slot di bawah, lalu kirim 1 emoji untuk slot itu.\n\n"
            "3 cara input yang diterima:\n"
            "• Emoji unicode biasa (ketik langsung, mis. 🔥)\n"
            "• TEMPEL Custom Emoji Telegram Premium (desain asli disimpan)\n"
            "• <b>ID Emoji</b> — ketik angka ID-nya saja, mis. <code>5368324170671202286</code>\n\n"
            "_Semua cara di atas akan dirender via <tg-emoji> — "
            "SEMUA user (free maupun premium) bisa melihatnya._\n\n"
            f"<b>Slot saat ini:</b>\n{preview}",
            parse_mode="HTML",
            reply_markup=_emoji_slot_keyboard(cat, defaults)
        )
        return

    info = _EMOJI_CAT_INFO.get(cat)
    if not info:
        return await query.answer("❌ Kategori tidak dikenal", show_alert=True)

    await _show_emoji_cat_page(query, uid, cat, page=0)

async def _show_emoji_cat_page(query, uid: str, cat: str, page: int):
    """Render one page of an emoji category's editable list.

    Telegram limits copy_text to 256 characters, so long lists (countries,
    button slots) are split into pages that each fit safely under that
    limit — this is what makes the "Salin" button actually work instead of
    silently failing to update the message."""
    info = _EMOJI_CAT_INFO[cat]
    all_lines = info["lines_fn"]()
    pages = _chunk_lines(all_lines, max_chars=230)
    page = max(0, min(page, len(pages) - 1))
    chunk = pages[page] if pages else []
    chunk_text = "\n".join(chunk)
    page_label = f" (halaman {page + 1}/{len(pages)})" if len(pages) > 1 else ""

    msg = (
        f"{info['title']}\n\n"
        f"{info['desc']}\n\n"
        f"<b>List saat ini{page_label} (salin & edit):</b>\n"
        f"<pre>{chunk_text}</pre>\n\n"
        f"💡 <i>Tekan <b>Salin</b> → edit emojinya saja → kirim balik "
        f"(boleh kirim hanya baris yang berubah).</i>"
    )
    get_session(uid)["state"] = info["state"]
    get_session(uid)["data"]  = {"cat": cat, "page": page}

    rows = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Sebelumnya", callback_data=f"emoji_cat_page:{cat}:{page-1}"))
    if page < len(pages) - 1:
        nav_row.append(InlineKeyboardButton("Berikutnya ▶", callback_data=f"emoji_cat_page:{cat}:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(
        "📋 Salin Halaman Ini" if len(pages) > 1 else "📋 Salin List",
        copy_text=CopyTextButton(text=chunk_text[:256] or " "),
        api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("copy_all", "📋"))
    )])
    rows.append([mkbtn("a_emoji_cancel", "Batal", callback_data="emoji_cat_back", style="danger")])

    await query.edit_message_text(
        msg[:4096],
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_emoji_cat_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prev/Next pagination for long emoji category lists (country, button, ...)."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    _, cat, page_str = query.data.split(":", 2)
    await _show_emoji_cat_page(query, uid, cat, page=int(page_str))

async def cb_emoji_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tap salah satu slot (mis. p1, e3) → minta kirim 1 emoji utk slot itu."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    _, category, slot = query.data.split(":", 2)
    get_session(uid)["state"] = "admin_set_emoji_slot"
    get_session(uid)["data"]  = {"cat": category, "slot": slot}

    # Build current value for the slot so admin can copy & replace just the emoji
    _default_map = _template_defaults_dynamic() if category == "template" else _PREMIUM_EMOJI_DEFAULTS
    _cur_entry   = _emoji_slot(category, slot, _default_map.get(slot, "✨"))
    _cur_char    = _cur_entry.get("char", "✨")
    _cur_id      = _cur_entry.get("id", "")
    # Copy text: ID if set (most useful to paste & replace), else the char
    _copy_val    = _cur_id if _cur_id else _cur_char
    _copy_label  = f"📋 Salin ID ({_cur_char})" if _cur_id else f"📋 Salin Emoji ({_cur_char})"

    await query.edit_message_text(
        f"✏️ <b>Set emoji untuk slot</b> <code>{slot}</code>\n\n"
        f"Nilai saat ini: {_cur_char}"
        + (f"  |  ID: <code>{_cur_id}</code>" if _cur_id else "") +
        "\n\n"
        "Kirim salah satu dari:\n"
        "• Emoji biasa (ketik langsung, mis. 🔥)\n"
        "• TEMPEL Custom Emoji Telegram Premium (desain aslinya disimpan)\n"
        "• <b>ID Emoji</b> — ketik angka ID-nya saja\n"
        "  <code>5368324170671202286</code>\n\n"
        "💡 <i>Tekan <b>Salin</b> untuk menyalin nilai saat ini, lalu ganti emojinya.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                _copy_label,
                copy_text=CopyTextButton(text=_copy_val),
                api_kwargs=_make_btn_kwargs("success", get_btn_emoji_id("copy_all", "📋"))
            )],
            [mkbtn("a_emoji_cancel", "Batal", callback_data="emoji_cat_back", style="danger")]
        ])
    )

async def cb_emoji_cat_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text(
        "🎨 <b>Custom Emoji</b>\n\nPilih kategori:",
        parse_mode="HTML",
        reply_markup=_emoji_custom_keyboard()
    )

async def cb_emoji_reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer("♻️ Semua emoji direset ke default")
    emoji_db_reset_all()
    global emoji_settings
    emoji_settings = emoji_db_load_all()
    _apply_emoji_overrides()
    await query.edit_message_text(
        "♻️ <b>Semua emoji berhasil direset ke default!</b>",
        parse_mode="HTML",
        reply_markup=_emoji_custom_keyboard()
    )

def _is_emoji_id(val: str) -> bool:
    """Return True kalau <code>val</code> adalah ID emoji Telegram — yaitu string angka
    panjang (minimal 10 digit, tanpa karakter lain)."""
    return bool(val) and val.isdigit() and len(val) >= 10

def _parse_emoji_lines(raw_text: str, entities=None) -> list:
    """Parse <code>key= emoji</code> (atau <code>key=emoji</code>) lines menjadi list of
    (key, emoji_char, custom_emoji_id). <code>raw_text</code> HARUS teks pesan asli
    (belum di-<code>.strip()</code>) supaya offset entity Telegram (UTF-16) tetap akurat.

    Tiga cara input nilai yang didukung:
    1. Emoji unicode biasa  → val=char, custom_id=None
    2. Custom Emoji Premium ditempel → val=char (via _utf16_slice), custom_id=ID entity
    3. Emoji ID diketik (angka ≥10 digit) → val="✨" (placeholder), custom_id=ID

    Semua kasus yang punya custom_id akan dirender via <tg-emoji> sehingga
    SEMUA user (gratis maupun premium) melihat desain aslinya.

    PENTING: untuk ekstraksi karakter emoji dari entity, SELALU pakai _utf16_slice
    bukan slicing Python biasa — Telegram offset/length adalah UTF-16 code unit,
    bukan Unicode code point!"""
    entities = list(entities or [])
    # Kumpulkan semua entity custom_emoji dengan offset & id-nya
    customs = [
        e for e in entities
        if e.type == "custom_emoji" and e.custom_emoji_id
    ]
    result = []
    cum = 0
    for line in raw_text.split("\n"):
        line_len   = _utf16_len(line)
        line_start = cum
        line_end   = cum + line_len
        cum        = line_end + 1   # +1 untuk '\n' antar baris

        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        idx = stripped.index("=")
        key = stripped[:idx].strip()
        val = stripped[idx + 1:].strip()
        if not key or not val:
            continue

        custom_id = None

        # Prioritas 1: Custom Emoji Telegram ditempel → entity di dalam baris ini
        ce = next(
            (e for e in customs if line_start <= e.offset < line_end),
            None
        )
        if ce:
            # Ekstrak karakter via UTF-16 slicing (bukan Python indexing!)
            char_via_utf16 = _utf16_slice(raw_text, ce.offset, ce.length)
            val       = char_via_utf16 if char_via_utf16 else val
            custom_id = str(ce.custom_emoji_id)

        # Prioritas 2: nilai adalah angka panjang → emoji ID diketik manual
        elif _is_emoji_id(val):
            custom_id = val
            val       = "✨"  # placeholder; <tg-emoji> tampilkan desain asli

        result.append((key, val, custom_id))
    return result

def _apply_service_emoji_edits(parsed: list) -> int:
    """Simpan langsung ke database per service yang cocok. Return jumlah entri yang cocok."""
    name_to_id = {v["name"]: k for k, v in services.items()}
    id_to_id   = {k: k for k in services}   # juga daftarkan svc_id langsung
    matched = 0
    for name_or_id, emoji, custom_id in parsed:
        svc_id = name_to_id.get(name_or_id) or id_to_id.get(name_or_id.lower())
        if svc_id and svc_id in services:
            emoji_db_set("service", svc_id, emoji, custom_id, "admin")
            matched += 1
    return matched

def _apply_country_emoji_edits(parsed: list) -> int:
    """Simpan langsung ke database per kode negara. Return jumlah entri yang cocok."""
    matched = 0
    for code, emoji, custom_id in parsed:
        code = re.sub(r"\D", "", code)
        if code:
            emoji_db_set("country", code, emoji, custom_id, "admin")
            matched += 1
    return matched

async def cb_view_premium_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan galeri emoji Premium ke semua user (free maupun premium)."""
    query = update.callback_query
    await query.answer()
    any_custom = False
    lines = ["👑 <b>Emoji Premium — Galeri</b>", ""]
    for key, default in _PREMIUM_EMOJI_DEFAULTS.items():
        entry = _emoji_slot("premium", key, default)
        if (emoji_settings.get("premium", {}) or {}).get(key):
            any_custom = True
        lines.append(f"  {emoji_html(entry)}  <code>{key}</code>")
    if not any_custom:
        lines.append("\n<i>(belum ada emoji premium yang diatur admin — masih default)</i>")
    svc_em = emoji_settings.get("service", {}) or {}
    if svc_em:
        lines.append("\n<b>📱 Emoji Service Kustom:</b>")
        for svc_id, entry in list(svc_em.items())[:10]:
            svc_name = services.get(svc_id, {}).get("name", svc_id)
            lines.append(f"  {emoji_html(entry)}  {svc_name}")
    lines.append("\n<i>Emoji di atas berlaku di semua tampilan bot.</i>")
    msg = "\n".join(lines)
    await query.edit_message_text(
        msg, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            mkbtn("back", "Kembali", callback_data="goto_main", style="primary")
        ]])
    )

async def cb_admin_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.answer()
    sess = get_session(uid)
    sess["is_admin"] = False
    sess["state"]    = None
    await query.edit_message_text("🚪 <b>Admin Logged Out.</b>", parse_mode="HTML")

async def cb_admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    buttons = []
    for cc, svcs in numbers_by_cs.items():
        for svc_id, nums in svcs.items():
            if nums:
                buttons.append([mkbtn("a_delete", f"🗑️ +{cc}/{svc_id} ({len(nums)})", callback_data=f"del_confirm:{cc}:{svc_id}", style="success", auto_icon=False)])
    buttons.append([mkbtn("a_confirm_no", "Cancel", callback_data="admin_back", style="danger")])
    await query.edit_message_text("🗑️ <b>Delete Numbers</b>\n\nSelect to delete:", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_del_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    _, cc, svc_id = query.data.split(":")
    count = len(numbers_by_cs.get(cc, {}).get(svc_id, []))
    await query.edit_message_text(
        f"⚠️ <b>Confirm Deletion</b>\n\nDelete {count} numbers from +{cc}/{svc_id}?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("verify", "Yes", callback_data=f"del_exec:{cc}:{svc_id}", style="success"),
             mkbtn("back", "No", callback_data="admin_back", style="success")],
        ])
    )

async def cb_del_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    _, cc, svc_id = query.data.split(":")
    count = len(numbers_by_cs.get(cc, {}).get(svc_id, []))
    if cc in numbers_by_cs and svc_id in numbers_by_cs[cc]:
        del numbers_by_cs[cc][svc_id]
        if not numbers_by_cs[cc]:
            del numbers_by_cs[cc]
    # bersihkan juga tracker siklus supaya tidak menyimpan nomor yang sudah dihapus
    if cc in numbers_used_cycle and svc_id in numbers_used_cycle[cc]:
        del numbers_used_cycle[cc][svc_id]
        if not numbers_used_cycle[cc]:
            del numbers_used_cycle[cc]
        await async_save_numbers_cycle()
    await async_save_numbers()
    await query.edit_message_text(f"✅ <b>Deleted {count} numbers.</b>", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")]]))
    # Note: no user broadcast on delete — only admin sees the result above

async def cb_goto_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Done.", parse_mode="HTML")

# ─── Document Handler ───
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    sess = get_session(uid)

    if sess.get("state") != "admin_upload_file":
        return

    doc   = update.message.document
    fname = (doc.file_name or "").lower()

    if not (fname.endswith(".txt") or fname.endswith(".xlsx") or fname.endswith(".xls")):
        return await update.message.reply_text("❌ Only .txt or .xlsx files are supported.")

    svc_id = (sess.get("data") or {}).get("serviceId", "other")
    added  = 0
    added_ccs = set()
    file   = await context.bot.get_file(doc.file_id)

    if fname.endswith(".xlsx") or fname.endswith(".xls"):
        try:
            import openpyxl, io
            raw = await file.download_as_bytearray()
            wb  = openpyxl.load_workbook(io.BytesIO(bytes(raw)), read_only=True, data_only=True)
            ws  = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                for cell in row:
                    if cell is None:
                        continue
                    num = re.sub(r"\D", "", str(cell))
                    if not re.match(r"^\d{10,15}$", num):
                        continue
                    cc = get_country_code_from_number(num)
                    if not cc:
                        continue
                    numbers_by_cs.setdefault(cc, {}).setdefault(svc_id, [])
                    if num not in numbers_by_cs[cc][svc_id]:
                        numbers_by_cs[cc][svc_id].append(num)
                        added += 1
                        added_ccs.add(cc)
                    break
        except Exception as e:
            logger.error(f"XLSX parse error: {e}")
            return await update.message.reply_text(f"❌ Excel file read error: {e}")
    else:
        raw_content = await file.download_as_bytearray()
        lines = raw_content.decode("utf-8", errors="ignore").split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                parts = line.split("|")
                num = parts[0].strip()
                cc  = parts[1].strip() if len(parts) > 1 else get_country_code_from_number(num)
                svc = parts[2].strip() if len(parts) > 2 else svc_id
            else:
                num = re.sub(r"\D", "", line)
                cc  = get_country_code_from_number(num)
                svc = svc_id
            if not re.match(r"^\d{10,15}$", num) or not cc:
                continue
            numbers_by_cs.setdefault(cc, {}).setdefault(svc, [])
            if num not in numbers_by_cs[cc][svc]:
                numbers_by_cs[cc][svc].append(num)
                added += 1
                added_ccs.add(cc)

    await async_save_numbers()
    sess["state"] = None
    sess["data"]  = None

    # Build cc_counts: how many numbers were added per country for this service
    cc_counts = {}
    for cc in added_ccs:
        cc_counts[cc] = len(numbers_by_cs.get(cc, {}).get(svc_id, []))

    svc_info  = services.get(svc_id, {"icon": "📞", "name": svc_id})
    svc_icon_html = get_svc_icon_html(svc_id)
    country_summary = ", ".join(
        f"{get_country_flag_html(c)} {html.escape(str(countries.get(c, {'name': c})['name']))}"
        for c in list(added_ccs)[:5]
    )
    total_all = count_total_available_numbers()
    upload_summary_text = (
        f"✅ <b>{added} nomor berhasil diupload!</b>\n\n"
        f"📞 <b>Service:</b> {svc_icon_html} {html.escape(str(svc_info['name']))}\n"
        + (f"🌍 <b>Negara:</b> {country_summary}\n" if country_summary else "") +
        f"➕ <b>Nomor Baru:</b> {added}\n"
        f"📊 <b>Total Tersedia Sekarang:</b> {total_all}"
    )
    try:
        await update.message.reply_text(upload_summary_text, parse_mode="HTML")
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        await update.message.reply_text(_strip_tg_emoji_tags(upload_summary_text), parse_mode="HTML")
    if added > 0:
        # 1 simple upload notify to all admins (no uploader name, just the stats)
        await notify_admins(
            context,
            f"📤 <b>File Baru Diupload</b>\n\n"
            f"📁 File: `{doc.file_name}`\n"
            f"📞 Service: {svc_icon} {svc_info['name']}\n"
            f"🌍 Negara: {country_summary}\n"
            f"➕ <b>Nomor Baru:</b> *{added}*\n"
            f"📦 <b>Total Tersedia:</b> *{total_all}*\n"
            f"🕐 {now_wib().strftime('%H:%M:%S')}",
            exclude_uid=uid
        )
        asyncio.create_task(broadcast_stock_notify(
            context,
            svc_id=svc_id,
            cc_counts=cc_counts,
            total=added,
            total_all=total_all,
        ))

# ─── Main Text Handler ───
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global emoji_settings
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    uid  = str(user.id)
    text = update.message.text.strip()

    if uid not in users:
        users[uid] = {
            "id": uid, "username": user.username or "no_username",
            "first_name": user.first_name or "User", "last_name": user.last_name or "",
            "joined": now_wib().isoformat(), "last_active": now_wib().isoformat(),
            "verified": False, "referredBy": None, "referralCount": 0,
        }
    users[uid]["last_active"] = now_wib().isoformat()
    await async_save_users()

    sess = get_session(uid)
    if not sess.get("is_admin") and is_admin(uid):
        sess["is_admin"] = True
    state = sess.get("state")

    # ── Menu bawah (reply keyboard) berwarna — tombolnya kirim text biasa, route ke handler yang sama
    # dengan tombol menu inline supaya perilakunya identik. Menekan tombol menu selalu membatalkan
    # state yang sedang berjalan (sama seperti /cancel).
    _menu_labels = reply_menu_labels()
    if text in _menu_labels:
        action = _menu_labels[text]
        handler = MENU_HANDLERS.get(action)
        sess["state"] = None
        sess["data"] = None
        # OTP hanya boleh dikirim ke user kalau nomornya masih tampil di
        # menu Get Number (lihat _number_still_assigned). Begitu user pindah
        # ke menu LAIN (Profil/Tools/Support/Live Traffic/Cari OTP/dll) —
        # bukan cuma saat minta nomor baru — daftar nomor yang lagi tampil
        # otomatis dianggap sudah tidak relevan lagi, jadi dilepas di sini
        # supaya OTP untuk nomor lama tidak lanjut terkirim ke user tsb.
        # handle_get_numbers sendiri sudah punya logika rilis-nya sendiri,
        # jadi tidak perlu dirilis dobel di sini.
        if action != "getnumber" and sess["current_numbers"]:
            await release_numbers_for_user(context, uid, sess["current_numbers"])
            sess["current_numbers"] = []
        if handler:
            await handler(update, context)
        return

    if state == "searching_otp":
        sess["state"] = None
        await run_otp_search_and_reply(update, context, uid, text)
        return

    if state == "wa_waiting_number":
        sess["state"] = None
        phone = re.sub(r"\D", "", text)
        if len(phone) < 10 or len(phone) > 15:
            return await update.message.reply_text("❌ Invalid number. Example: <code>8801712345678</code>", parse_mode="HTML")

        loading = await update.message.reply_text(
            "⏳ <b>Fetching pairing code...</b>\n\n⌛ Please wait a few seconds.",
            parse_mode="HTML"
        )

        async def wa_task():
            try:
                # আগে check করো connected কিনা
                current_state = await green_get_state(uid)
                if current_state == "authorized":
                    wa_sessions[uid] = {"connected": True}
                    try: await loading.delete()
                    except: pass
                    await context.bot.send_message(
                        uid,
                        "✅ <b>WhatsApp Already Connected!</b>\n\n"
                        "🟢 Your WhatsApp is already connected.",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [mkbtn("wa_disconnect", "Logout / Disconnect", callback_data="wa_disconnect", style="danger")],
                            [mkbtn("wa_status", "Check Status", callback_data="wa_status", style="primary")],
                        ])
                    )
                    return

                code = await get_wa_pairing_code(phone, uid)
                clean_code = re.sub(r"[^A-Z0-9]", "", code.upper())
                formatted = (clean_code[:4] + "-" + clean_code[4:8]) if len(clean_code) >= 8 else code
                try: await loading.delete()
                except: pass
                await context.bot.send_message(
                    uid,
                    f"🔑 <b>Pairing Code</b>\n\n"
                    f"`{formatted}`\n\n"
                    f"📋 <b>Steps:</b>\n"
                    f"1. Open WhatsApp\n"
                    f"2. Settings → Linked Devices\n"
                    f"3. Link a Device → <b>Link with phone number</b>\n"
                    f"4. Enter the code above\n\n"
                    f"✅ After entering the code, press <b>Check Status</b>.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [mkbtn("wa_status", "Check Status", callback_data="wa_status", style="primary")],
                        [mkbtn("wa_connect", "New Code", callback_data="wa_connect", style="success")],
                    ])
                )
                asyncio.create_task(monitor_wa_connection(uid, context))
            except Exception as e:
                try: await loading.delete()
                except: pass
                logger.error(f"WA error: {e}", exc_info=True)
                await context.bot.send_message(
                    uid,
                    f"❌ <b>Connection failed:</b> {str(e)[:150]}\n\nPlease try again in a moment.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[mkbtn("wa_connect", "Try Again", callback_data="wa_connect", style="success")]])
                )

        asyncio.create_task(wa_task())
        return

    pending_totp_svc = users.get(uid, {}).get("pending_totp_svc")
    if state == "totp_waiting_secret" or pending_totp_svc:
        sess["state"] = None
        svc = (sess.get("data") or {}).get("service") or pending_totp_svc or "other"

        if uid in users and "pending_totp_svc" in users[uid]:
            del users[uid]["pending_totp_svc"]
            await async_save_users()

        try:
            result = generate_totp(text)
        except Exception as e:
            logger.error(f"TOTP exception uid={uid}: {e}")
            result = None

        if not result:
            await update.message.reply_text(
                "❌ <b>Invalid secret key!</b>\n\n"
                "The key is invalid. Please copy the exact secret key from your authenticator app.\n"
                "Example format: <code>JBSWY3DPEHPK3PXP</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [mkbtn("totp_refresh", "Try Again", callback_data=f"totp:{svc}", style="primary")],
                    [mkbtn("totp_back", "Back", callback_data="totp_back", style="primary")],
                ])
            )
            return

        icons = {"facebook": "📘", "instagram": "📸", "google": "🔍", "other": "⚙️"}
        names = {"facebook": "Facebook", "instagram": "Instagram", "google": "Google", "other": "2FA"}
        icon  = icons.get(svc, "🔐")
        name  = names.get(svc, svc)

        secret_quoted = urllib.parse.quote(text)
        cb_data = f"totp_r:{svc}:{secret_quoted}"
        if len(cb_data.encode()) > 62:
            cb_data = f"totp_r:{svc}:TOOLONG"

        try:
            await update.message.reply_text(
                f"{icon} <b>{name} 2FA Code</b>\n\n"
                f"🔑 <b>Code:</b> `{result['token']}`\n\n"
                f"⏰ <b>{result['timeRemaining']} seconds remaining</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [mkbtn("totp_refresh", "Refresh Code", callback_data=cb_data, style="primary")],
                    [mkbtn("totp_back", "Back", callback_data="totp_back", style="primary")],
                ])
            )
        except Exception as e:
            logger.error(f"TOTP reply error uid={uid}: {e}")
            await update.message.reply_text(f"✅ 2FA Code: {result['token']} (⏰ {result['timeRemaining']}s)")
        return

    if state == "w_account":
        sess["state"] = None
        data   = sess.get("data", {})
        method = data.get("method", "bKash")
        amount = data.get("amount", 0)
        e      = get_user_earnings(uid)

        if amount > e["balance"]:
            return await update.message.reply_text("❌ Insufficient balance!")

        icon = "🟣" if method == "bKash" else "🟠"
        sess["state"] = "w_confirm"
        sess["data"]  = {"method": method, "amount": amount, "account": text}

        await update.message.reply_text(
            f"{icon} <b>Confirm Withdrawal</b>\n\n"
            f"💳 Method: {method}\n"
            f"📱 Account: `{text}`\n"
            f"💵 Amount: <b>{amount:.2f} USD</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [mkbtn("verify", "Confirm", callback_data="w_confirm", style="success"),
                 mkbtn("w_cancel", "Cancel", callback_data="w_cancel", style="danger")],
            ])
        )
        return

    if state == "admin_set_referral_commission" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = float(text)
            if 0 <= val <= 50:
                settings["referralCommission"] = val
                save_settings()
                await update.message.reply_text(
                    f"✅ <b>Referral commission set to {val:.1f}%</b>\n\n"
                    f"From now on, each OTP will give the referrer {val:.1f}% commission.",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Please enter a value between 0 and 50.")
        except:
            await update.message.reply_text("❌ Invalid number. Example: <code>10</code>", parse_mode="HTML")
        return

    if state == "global_wa_phone" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        phone = re.sub(r"\D", "", text.strip())
        if len(phone) < 8:
            return await update.message.reply_text("❌ Invalid number!")
        loading = await update.message.reply_text("⏳ Connecting Global WhatsApp...")
        try:
            code = await get_wa_pairing_code(phone, f"global_{uid}")
            if not code:
                await loading.delete()
                return await update.message.reply_text("❌ Pairing code not received. Please try again.")
            global_wa_data["phone"]     = phone
            global_wa_data["uid"]       = f"global_{uid}"
            global_wa_data["connected"] = False
            save_global_wa()
            await loading.delete()
            await update.message.reply_text(
                f"📱 <b>Global WhatsApp Pairing Code:</b>\n\n"
                f"`{code}`\n\n"
                f"WhatsApp → Linked Devices → Link a Device → Enter code",
                parse_mode="HTML"
            )
            # verify loop
            async def verify_global_wa():
                for _ in range(20):
                    await asyncio.sleep(15)
                    state_check = await green_get_state(f"global_{uid}")
                    if state_check == "authorized":
                        wa_sessions[f"global_{uid}"] = {"connected": True}
                        global_wa_data["connected"] = True
                        global_wa_data["enabled"]   = True
                        save_global_wa()
                        try:
                            await context.bot.send_message(
                                int(uid),
                                "✅ <b>Global WhatsApp Connected!</b>\n\n"
                                "All user numbers will now be checked via this WhatsApp.",
                                parse_mode="HTML"
                            )
                        except: pass
                        return
            asyncio.create_task(verify_global_wa())
        except Exception as e:
            await loading.delete()
            await update.message.reply_text(f"❌ Error: {e}")
        return

    if state == "sc_panel_wizard" and (sess["is_admin"] or is_admin(uid)):
        st = sess.get("data") or {}
        action = st.get("action")

        if action == "add_builtin":
            if "username" not in st:
                st["username"] = text.strip()
                sess["data"] = st
                next_label = "API key/token" if _panel_uses_api_token(st.get("ptype")) else "password"
                await update.message.reply_text(f"🔑 Enter <b>{next_label}</b>:", parse_mode="HTML")
            elif "password" not in st:
                st["password"] = text.strip()
                sess["data"] = st
                if _is_webhook_panel(st.get("ptype")):
                    await update.message.reply_text(
                        "🌐 <b>Webhook URL akun (opsional)</b>\n"
                        "Kirim URL publik webhook, atau ketik <code>skip</code>:",
                        parse_mode="HTML",
                    )
                else:
                    default_interval = _panel_delay(st.get("ptype"))
                    minimum_interval = _panel_min_poll_interval(st.get("ptype"))
                    await update.message.reply_text(
                        "⏱️ Masukkan interval polling akun dalam detik "
                        f"(<b>{minimum_interval}-{POLL_INTERVAL_MAX_SECONDS}</b>, "
                        f"default panel: <b>{default_interval}s</b>):",
                        parse_mode="HTML",
                    )
            elif _is_webhook_panel(st.get("ptype")) and "webhook_url" not in st:
                webhook_url = _clean_optional_webhook_value(text)
                url_error = _webhook_url_error(webhook_url)
                if url_error:
                    return await update.message.reply_text(
                        f"❌ {url_error}\nKetik URL publik https:// atau <code>skip</code>.",
                        parse_mode="HTML",
                    )
                st["webhook_url"] = webhook_url
                sess["data"] = st
                if _webhook_requires_secret(st.get("ptype")):
                    await update.message.reply_text(
                        "🔐 <b>Secret key webhook akun (wajib)</b>\n"
                        "Salin signing secret dari provider:",
                        parse_mode="HTML",
                    )
                else:
                    default_interval = _panel_delay(st.get("ptype"))
                    minimum_interval = _panel_min_poll_interval(st.get("ptype"))
                    await update.message.reply_text(
                        "⏱️ <b>Polling interval</b> dalam detik (opsional)\n"
                        f"Ketik angka {minimum_interval}-{POLL_INTERVAL_MAX_SECONDS}, "
                        f"atau <code>skip</code> untuk default {default_interval} detik:",
                        parse_mode="HTML",
                    )
            elif _webhook_requires_secret(st.get("ptype")) and "webhook_secret" not in st:
                webhook_secret = _clean_optional_webhook_value(text)
                if not webhook_secret:
                    return await update.message.reply_text(
                        "❌ Secret webhook wajib diisi agar signature dapat diverifikasi.",
                        parse_mode="HTML",
                    )
                st["webhook_secret"] = webhook_secret
                sess["data"] = st
                default_interval = _panel_delay(st.get("ptype"))
                minimum_interval = _panel_min_poll_interval(st.get("ptype"))
                await update.message.reply_text(
                    "⏱️ <b>Polling interval</b> dalam detik (opsional)\n"
                    f"Ketik angka {minimum_interval}-{POLL_INTERVAL_MAX_SECONDS}, "
                    f"atau <code>skip</code> untuk default {default_interval} detik:",
                    parse_mode="HTML",
                )
            else:
                bn    = st["panel_name"]
                uname = st["username"]
                interval = _optional_poll_interval(text, st.get("ptype")) if _is_webhook_panel(st.get("ptype")) else _parse_poll_interval(text)
                if interval is None:
                    minimum_interval = _panel_min_poll_interval(st.get("ptype"))
                    return await update.message.reply_text(
                        f"❌ Interval harus angka {minimum_interval}-"
                        f"{POLL_INTERVAL_MAX_SECONDS} detik. Contoh: <code>{minimum_interval}</code>.",
                        parse_mode="HTML",
                    )
                pwd   = st["password"]
                with db_conn() as c:
                    c.execute("INSERT OR REPLACE INTO panels(name,url,ptype,fp) VALUES(?,?,?,?)",
                              (bn, st["url"], st["ptype"], st.get("fp")))
                    c.execute(
                        "INSERT INTO accounts(panel_name,username,password,poll_interval,webhook_url,webhook_secret) "
                        "VALUES(?,?,?,?,?,?)",
                        (bn, uname, pwd, interval, st.get("webhook_url", ""), st.get("webhook_secret", "")),
                    )
                sess["state"] = None
                sess["data"]  = None
                p = get_panel(bn)
                started = start_panel(p, context.application)
                await update.message.reply_text(
                    f"✅ <b>{bn}</b> added{' & started' if started else ' (no start — check accounts)'}!\n"
                    f"Account: `{uname}`\n⏱️ Polling: <b>{interval}s</b>"
                    + (f"\n🌐 Webhook: <code>{html.escape(st.get('webhook_url') or 'default route')}</code>" if _is_webhook_panel(st.get("ptype")) else ""),
                    parse_mode="HTML"
                )
            return

        if action == "add_custom":
            if "panel_name" not in st:
                st["panel_name"] = text.strip()
                sess["data"] = st
                await update.message.reply_text("🌐 Enter panel <b>URL</b>:", parse_mode="HTML")
            elif "url" not in st:
                st["url"] = text.strip()
                sess["data"] = st
                await update.message.reply_text("🔧 Select panel <b>type</b>:", parse_mode="HTML", reply_markup=kb_ptype())
            return

        if action == "add_account":
            bn = st["panel_name"]
            panel = get_panel(bn)
            if "username" not in st:
                st["username"] = text.strip()
                sess["data"] = st
                next_label = "API key/token" if panel and _panel_uses_api_token(panel["ptype"]) else "password"
                await update.message.reply_text(f"🔑 Enter <b>{next_label}</b>:", parse_mode="HTML")
            elif "password" not in st:
                st["password"] = text.strip()
                sess["data"] = st
                panel = get_panel(bn)
                if panel and _is_webhook_panel(panel["ptype"]):
                    await update.message.reply_text(
                        "🌐 <b>Webhook URL akun (opsional)</b>\n"
                        "Kirim URL publik webhook, atau ketik <code>skip</code>:",
                        parse_mode="HTML",
                    )
                else:
                    default_interval = _panel_delay(panel["ptype"]) if panel else 3
                    minimum_interval = _panel_min_poll_interval(panel["ptype"]) if panel else POLL_INTERVAL_MIN_SECONDS
                    await update.message.reply_text(
                        "⏱️ Masukkan interval polling akun dalam detik "
                        f"(<b>{minimum_interval}-{POLL_INTERVAL_MAX_SECONDS}</b>, "
                        f"default panel: <b>{default_interval}s</b>):",
                        parse_mode="HTML",
                    )
            elif panel and _is_webhook_panel(panel["ptype"]) and "webhook_url" not in st:
                webhook_url = _clean_optional_webhook_value(text)
                url_error = _webhook_url_error(webhook_url)
                if url_error:
                    return await update.message.reply_text(
                        f"❌ {url_error}\nKetik URL publik https:// atau <code>skip</code>.",
                        parse_mode="HTML",
                    )
                st["webhook_url"] = webhook_url
                sess["data"] = st
                await update.message.reply_text(
                    "🔐 <b>Secret key webhook akun (wajib)</b>\n"
                    "Salin signing secret dari Augestel:",
                    parse_mode="HTML",
                )
            elif panel and _is_webhook_panel(panel["ptype"]) and "webhook_secret" not in st:
                webhook_secret = _clean_optional_webhook_value(text)
                if not webhook_secret:
                    return await update.message.reply_text(
                        "❌ Secret webhook wajib diisi agar signature Augestel dapat diverifikasi.",
                        parse_mode="HTML",
                    )
                st["webhook_secret"] = webhook_secret
                sess["data"] = st
                default_interval = _panel_delay(panel["ptype"])
                minimum_interval = _panel_min_poll_interval(panel["ptype"])
                await update.message.reply_text(
                    "⏱️ <b>Polling interval</b> dalam detik (opsional)\n"
                    f"Ketik angka {minimum_interval}-{POLL_INTERVAL_MAX_SECONDS}, "
                    f"atau <code>skip</code> untuk default {default_interval} detik:",
                    parse_mode="HTML",
                )
            else:
                interval = _optional_poll_interval(text, panel["ptype"]) if panel and _is_webhook_panel(panel["ptype"]) else _parse_poll_interval(text)
                if interval is None:
                    minimum_interval = _panel_min_poll_interval(panel["ptype"]) if panel else POLL_INTERVAL_MIN_SECONDS
                    return await update.message.reply_text(
                        f"❌ Interval harus angka {minimum_interval}-"
                        f"{POLL_INTERVAL_MAX_SECONDS} detik. Contoh: <code>{minimum_interval}</code>.",
                        parse_mode="HTML",
                    )
                uname = st["username"]
                pwd   = st["password"]
                with db_conn() as c:
                    c.execute(
                        "INSERT INTO accounts(panel_name,username,password,poll_interval,webhook_url,webhook_secret) "
                        "VALUES(?,?,?,?,?,?)",
                        (bn, uname, pwd, interval, st.get("webhook_url", ""), st.get("webhook_secret", "")),
                    )
                sess["state"] = None
                sess["data"]  = None
                p = get_panel(bn)
                if p and p["enabled"]:
                    stop_panel(bn)
                    start_panel(p, context.application)
                await update.message.reply_text(
                    f"✅ Account `{uname}` added to <b>{bn}</b>.\n"
                    f"⏱️ Polling: <b>{interval}s</b>"
                    + (f"\n🌐 Webhook: <code>{html.escape(st.get('webhook_url') or 'default route')}</code>" if panel and _is_webhook_panel(panel["ptype"]) else ""),
                    parse_mode="HTML",
                )
            return

        # Unknown wizard state — reset supaya tidak nyangkut
        sess["state"] = None
        sess["data"]  = None
        return

    if state == "admin_add_otp_group" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        gid = text.strip()
        if not re.match(r'^-?\d+$', gid):
            return await update.message.reply_text("❌ Chat ID harus berupa angka (contoh: <code>-1001234567890</code>).", parse_mode="HTML")
        add_otp_group(gid)
        await update.message.reply_text(f"✅ <b>Grup `{gid}` ditambahkan.</b>\n\nOTP akan mulai dikirim ke grup ini.", parse_mode="HTML")
        return

    if state == "admin_edit_otp_template" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            tmpl = json.loads(raw)
            if "text" not in tmpl or "buttons" not in tmpl:
                raise ValueError("JSON harus punya key 'text' dan 'buttons'")
            tmpl, n_emoji = _auto_attach_premium_emoji(tmpl, update.message)
            set_otp_template(tmpl)
            extra_msg = f"\n✨ {n_emoji} custom emoji premium terdeteksi & otomatis dipasang." if n_emoji else ""
            await update.message.reply_text(f"✅ <b>Template Grup berhasil disimpan!</b>{extra_msg}", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ <b>JSON tidak valid:</b> {e}\n\nCoba lagi atau ketik ulang dari awal.", parse_mode="HTML")
        return

    if state == "admin_edit_otp_user_template" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            tmpl = json.loads(raw)
            if "text" not in tmpl or "buttons" not in tmpl:
                raise ValueError("JSON harus punya key 'text' dan 'buttons'")
            tmpl, n_emoji = _auto_attach_premium_emoji(tmpl, update.message)
            set_otp_user_template(tmpl)
            extra_msg = f"\n✨ {n_emoji} custom emoji premium terdeteksi & otomatis dipasang." if n_emoji else ""
            await update.message.reply_text(f"✅ <b>Template User berhasil disimpan!</b>{extra_msg}", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ <b>JSON tidak valid:</b> {e}\n\nCoba lagi atau ketik ulang dari awal.", parse_mode="HTML")
        return

    if state == "admin_broadcast" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        sent = 0
        for target_uid in list(users.keys()):
            try:
                await context.bot.send_message(target_uid, text, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"✅ <b>Broadcast sent to {sent} users.</b>", parse_mode="HTML")
        return

    if state == "admin_add_numbers" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        added = 0
        added_pairs = set()
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                num, cc, svc = parts[0].strip(), parts[1].strip(), parts[2].strip()
            elif len(parts) == 2:
                num, cc, svc = parts[0].strip(), parts[1].strip(), "other"
            else:
                num = line
                cc  = get_country_code_from_number(num)
                svc = "other"
            if re.match(r"^\d{10,15}$", num) and cc:
                numbers_by_cs.setdefault(cc, {}).setdefault(svc, [])
                if num not in numbers_by_cs[cc][svc]:
                    numbers_by_cs[cc][svc].append(num)
                    added += 1
                    added_pairs.add((cc, svc))
        await async_save_numbers()

        # Group added numbers by svc for notification (one broadcast per service)
        svc_groups: dict = {}  # svc_id -> {cc: count}
        for cc, svc in added_pairs:
            svc_groups.setdefault(svc, {})
            svc_groups[svc][cc] = len(numbers_by_cs.get(cc, {}).get(svc, []))

        # Reply summary to admin
        summary_lines = []
        for svc, cc_map in list(svc_groups.items())[:5]:
            sv = services.get(svc, {"icon": "📞", "name": svc})
            for cc, cnt in list(cc_map.items())[:3]:
                ctr = countries.get(cc, {"flag": "🌍", "name": cc})
                summary_lines.append(f"• {get_svc_icon_html(svc)} {html.escape(str(sv.get('name', svc)))} — {get_country_flag_html(cc)} {html.escape(str(ctr.get('name', cc)))} ({cnt})")
        summary_text = "\n".join(summary_lines) if summary_lines else ""
        try:
            await update.message.reply_text(
                f"✅ <b>{added} numbers added!</b>\n\n" + (summary_text + "\n" if summary_text else ""),
                parse_mode="HTML"
            )
        except Exception as e:
            if not _is_emoji_related_error(e):
                raise
            logger.warning(f"⚠️ Reply summary dgn custom emoji premium gagal ({e}) — coba ulang pakai emoji biasa.")
            await update.message.reply_text(
                _strip_tg_emoji_tags(f"✅ <b>{added} numbers added!</b>\n\n" + (summary_text + "\n" if summary_text else "")),
                parse_mode="HTML"
            )
        if added > 0:
            await notify_admins(
                context,
                f"➕ <b>Numbers Added</b>\n\n"
                f"👤 Admin: {user.first_name} (`{uid}`)\n"
                + (f"{summary_text}\n" if summary_text else "") +
                f"📊 Total: <b>{added}</b> numbers\n"
                f"🕐 {now_wib().strftime('%H:%M:%S')}",
                exclude_uid=uid
            )
            # Broadcast one notification per service
            for svc, cc_map in svc_groups.items():
                svc_total = sum(cc_map.values())
                asyncio.create_task(broadcast_stock_notify(
                    context,
                    svc_id=svc,
                    cc_counts=cc_map,
                    total=svc_total,
                ))
        return

    if state == "admin_set_count" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = int(text)
            if 1 <= val <= 100:
                settings["defaultNumberCount"] = val
                save_settings()
                await update.message.reply_text(f"✅ <b>Number count set to {val}.</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Enter 1-100.")
        except:
            await update.message.reply_text("❌ Invalid number.")
        return

    if state == "admin_set_cooldown" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = int(text)
            if 1 <= val <= 3600:
                settings["cooldownSeconds"] = val
                save_settings()
                await update.message.reply_text(f"✅ <b>Cooldown set to {val} seconds.</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Enter 1-3600.")
        except:
            await update.message.reply_text("❌ Invalid number.")
        return

    if state == "admin_set_price" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = float(text)
            if val >= 0:
                settings["defaultOtpPrice"] = val
                save_settings()
                await update.message.reply_text(f"✅ <b>Default OTP price set to {val:.2f} USD.</b>", parse_mode="HTML")
        except:
            await update.message.reply_text("❌ Invalid price.")
        return

    if state == "admin_set_autodelete_minutes" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            minutes = int(text.strip())
        except ValueError:
            await update.message.reply_text("❌ Masukkan angka menit yang valid (mis. <code>10</code>).", parse_mode="HTML")
            return
        if not (1 <= minutes <= 10080):
            await update.message.reply_text("❌ Durasi harus antara 1–10080 menit (maks 7 hari).", parse_mode="HTML")
            return
        settings["autoDeleteOtpMinutes"] = minutes
        save_settings()
        on = settings.get("autoDeleteOtpEnabled", False)
        status_note = "" if on else "\n\n⚠️ Auto-Delete masih <b>OFF</b> — nyalakan dulu dari menu Auto-Delete OTP Grup."
        await update.message.reply_text(
            f"✅ <b>Durasi Auto-Delete diubah!</b>\n\n⏱ Durasi: *{minutes} menit*{status_note}",
            parse_mode="HTML"
        )
        return

    if state == "admin_set_minw" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = float(text)
            if val > 0:
                settings["minWithdraw"] = val
                save_settings()
                await update.message.reply_text(f"✅ <b>Min withdraw set to {val:.2f} USD.</b>", parse_mode="HTML")
        except:
            await update.message.reply_text("❌ Invalid amount.")
        return

    if state == "admin_set_otpwindow" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        try:
            val = int(text)
            if 1 <= val <= 1440:
                settings["otpSearchWindowMinutes"] = val
                save_settings()
                await update.message.reply_text(f"✅ <b>Cari OTP window set to {val} menit.</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Enter 1-1440.")
        except:
            await update.message.reply_text("❌ Invalid number.")
        return

    if state == "admin_set_cek_bio_url" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        url = text.strip()
        if url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/"):
            settings["cek_bio_wa_url"] = url
            save_settings()
            await update.message.reply_text(
                f"✅ <b>URL Cek Bio WA berhasil diperbarui!</b>\n\n🔵 `{url}`\n\n"
                f"Tombol <b>Cek Bio WA</b> di menu Tools sekarang mengarah ke URL ini.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "❌ URL tidak valid. Harus dimulai dengan <code>https://</code>, <code>http://</code>, atau <code>t.me/</code>.",
                parse_mode="HTML"
            )
        return

    if state == "admin_set_fix_merah_url" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        url = text.strip()
        if url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/"):
            settings["fix_merah_url"] = url
            save_settings()
            await update.message.reply_text(
                f"✅ <b>URL FIX Merah berhasil diperbarui!</b>\n\n🔴 `{url}`\n\n"
                f"Tombol <b>FIX Merah</b> di menu Tools sekarang mengarah ke URL ini.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "❌ URL tidak valid. Harus dimulai dengan <code>https://</code>, <code>http://</code>, atau <code>t.me/</code>.",
                parse_mode="HTML"
            )
        return

    if state == "admin_set_hidden_mask" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None

        # Deteksi input mask — tiga cara yang didukung (sama seperti Custom
        # Emoji per-slot lainnya), supaya admin bisa pakai emoji Premium juga:
        # 1. Tempel Custom Emoji Telegram Premium → entity custom_emoji dari Telegram
        # 2. Ketik ID emoji langsung (angka ≥ 10 digit)
        # 3. Teks/emoji unicode biasa diketik
        custom_id = None
        mask      = None

        # Prioritas 1: tempel Custom Emoji Premium → dapat entity dari Telegram
        customs = _extract_custom_emojis(update.message)
        if customs:
            first     = customs[0]
            mask      = first["char"]
            custom_id = first["id"]

        # Prioritas 2: teks adalah angka panjang → ID emoji diketik manual
        if not custom_id and _is_emoji_id(text.strip()):
            custom_id = text.strip()
            mask      = "✨"   # placeholder; <tg-emoji> akan tampilkan desain asli

        # Prioritas 3: teks/emoji unicode biasa
        if not mask:
            stripped = text.strip()
            if stripped:
                mask = stripped

        if not mask:
            await update.message.reply_text("❌ Mask tidak boleh kosong.", parse_mode="HTML")
            return
        if len(mask) > 20:
            await update.message.reply_text("❌ Mask maksimal 20 karakter.", parse_mode="HTML")
            return

        settings["hidden_number_mask"]    = mask
        settings["hidden_number_mask_id"] = custom_id
        save_settings()
        pfx     = int(settings.get("mask_prefix_digits", 4))
        sfx     = int(settings.get("mask_suffix_digits", 2))
        sample  = "628123456789"
        # emoji_html() supaya kalau mask barusan Custom Emoji Premium, preview
        # yang dikirim balik langsung menampilkan desain asli lewat <tg-emoji>,
        # bukan cuma karakter fallback (⭐/✨) seperti sebelumnya.
        mask_html    = emoji_html({"char": mask, "id": custom_id})
        preview_html = html.escape(sample[:pfx]) + mask_html + html.escape(sample[-sfx:] if sfx > 0 else "")
        premium_note = "\n✨ Tersimpan sebagai Custom Emoji Premium (tampil sama di semua user)." if custom_id else ""
        await update.message.reply_text(
            f"✅ <b>Mask berhasil diubah!</b>\n\n"
            f"🎭 Mask: `{mask_html}`\n"
            f"🔢 Depan: `{pfx}<code> digit  |  Belakang: </code>{sfx}` digit\n"
            f"👁 Preview: `{preview_html}`{premium_note}",
            parse_mode="HTML"
        )
        return

    if state == "admin_add_balance" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 2:
            try:
                target_id = parts[0]
                amount    = float(parts[1])
                # BUG FIX: sebelumnya amount tidak divalidasi, jadi admin bisa
                # (sengaja/salah ketik) memasukkan angka negatif atau 0 di
                # "Add Balance" — efeknya balance user bisa berkurang tanpa
                # batas bawah 0, beda dengan "Deduct Balance" yang sudah
                # di-floor ke 0.
                if amount <= 0:
                    return await update.message.reply_text("❌ Jumlah harus lebih dari 0.")
                e         = get_user_earnings(target_id)
                e["balance"] = round(e["balance"] + amount, 2)
                await async_save_earnings()
                await update.message.reply_text(f"✅ <b>{amount:.2f} USD added to {target_id}.</b>", parse_mode="HTML")
            except:
                await update.message.reply_text("❌ Error.")
        else:
            await update.message.reply_text("❌ Format: <code>[userId] [amount]</code>", parse_mode="HTML")
        return

    if state == "admin_deduct_balance" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 2:
            try:
                target_id = parts[0]
                amount    = float(parts[1])
                e         = get_user_earnings(target_id)
                e["balance"] = max(0, round(e["balance"] - amount, 2))
                await async_save_earnings()
                await update.message.reply_text(f"✅ <b>{amount:.2f} USD deducted from {target_id}.</b>", parse_mode="HTML")
            except:
                await update.message.reply_text("❌ Error.")
        return

    if state == "admin_reset_balance" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        target_id = text.strip()
        e = get_user_earnings(target_id)
        e["balance"] = 0
        await async_save_earnings()
        await update.message.reply_text(f"✅ <b>{target_id}'s balance reset to 0.</b>", parse_mode="HTML")
        return

    if state == "admin_set_country_price" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        updated = 0
        for line in text.split("\n"):
            parts = re.split(r"[:\s]+", line.strip())
            if len(parts) >= 2:
                cc    = re.sub(r"\D", "", parts[0])
                try:
                    price = float(parts[1])
                    if cc and price >= 0:
                        country_prices[cc] = price
                        updated += 1
                except:
                    pass
        save_cp()
        await update.message.reply_text(f"✅ <b>{updated} prices updated!</b>", parse_mode="HTML")
        return

    if state == "admin_add_country" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 3:
            cc   = re.sub(r"\D", "", parts[0])
            name = " ".join(parts[1:-1])
            flag = parts[-1]
            countries[cc] = {"name": name, "flag": flag}
            save_countries()
            await update.message.reply_text(f"✅ <b>Country added!</b>\n+{cc}: {flag} {name}", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Format: <code>[code] [name] [flag]</code>", parse_mode="HTML")
        return

    if state == "admin_add_service" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        parts = text.split()
        if len(parts) >= 3:
            svc_id   = parts[0].lower()
            svc_name = " ".join(parts[1:-1])
            icon     = parts[-1]
            services[svc_id] = {"name": svc_name, "icon": icon}
            save_services()
            await update.message.reply_text(f"✅ <b>Service added!</b>\n`{svc_id}`: {icon} {svc_name}", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Format: <code>[id] [name] [icon]</code>", parse_mode="HTML")
        return

    # ─── Custom Emoji: kategori massal (list `key= emoji` per baris) ───
    BULK_EMOJI_STATES = {
        "admin_set_emoji_service": ("service", _apply_service_emoji_edits),
        "admin_set_emoji_country": ("country", _apply_country_emoji_edits),
        "admin_set_emoji_button":  ("button",  None),
        "admin_set_emoji_other":   ("other",   None),
    }
    if state in BULK_EMOJI_STATES and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        category, apply_fn = BULK_EMOJI_STATES[state]
        # Pakai update.message.text MENTAH (belum di-strip) + entities asli
        # supaya offset Custom Emoji (kalau admin/​user Premium menempel emoji
        # asli, bukan sekadar mengetik) tetap akurat per baris.
        parsed = _parse_emoji_lines(update.message.text, update.message.entities)
        any_custom = any(cid for _, _, cid in parsed)
        if not parsed:
            await update.message.reply_text(
                "❌ <b>Tidak ada perubahan valid.</b>\n\nFormat: <code>nama/kode= emoji</code> satu per baris.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    mkbtn("admin_back", "Kembali", callback_data="admin_custom_emoji", style="primary")
                ]])
            )
            return
        if apply_fn:
            matched = apply_fn(parsed)
            if matched == 0:
                extra = ""
                if category == "service":
                    known = ", ".join(v["name"] for v in services.values())
                    extra = f" Service yang tersedia: {known or '(kosong)'}"
                await update.message.reply_text(
                    f"❌ <b>Tidak ada entri yang cocok.</b>{extra}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        mkbtn("admin_back", "Kembali", callback_data="admin_custom_emoji", style="primary")
                    ]])
                )
                return
        else:
            for key, emoji, custom_id in parsed:
                emoji_db_set(category, key, emoji, custom_id, uid)
            matched = len(parsed)
        emoji_settings = emoji_db_load_all()
        _apply_emoji_overrides()
        info = _EMOJI_CAT_INFO.get(category, {})
        updated_list = info.get("build_fn", lambda: "")() if info else ""
        preview_block = f"\n\n<b>Preview terbaru:</b>\n```\n{updated_list[:800]}\n```" if updated_list else ""
        realtime_note = (
            "\n\n✅ <i>Emoji langsung diterapkan ke semua tampilan bot (teks & tombol).</i>"
            if category in ("service", "country")
            else "\n\n✅ <i>Emoji tombol langsung diterapkan — menu bawah akan dikirim ulang di bawah ini.</i>"
            if category == "button"
            else ""
        )
        # Hitung berapa yang pakai emoji ID dan berapa yang tempel premium
        id_typed_count = sum(
            1 for _, char, cid in parsed if cid and char == "✨"
        )
        premium_pasted_count = sum(
            1 for _, char, cid in parsed if cid and char != "✨"
        )
        if any_custom:
            parts = []
            if premium_pasted_count:
                parts.append(f"{premium_pasted_count} Custom Emoji Telegram Premium ditempel")
            if id_typed_count:
                parts.append(f"{id_typed_count} emoji diset via ID langsung")
            note_detail = " & ".join(parts)
            premium_note = (
                f"\n🆔✨ _{note_detail} — desain aslinya akan tetap terlihat "
                "oleh SEMUA user (gratis maupun premium) via <tg-emoji>._"
            )
        else:
            premium_note = ""
        if category == "button" and any_custom:
            premium_note += (
                "\n💡 _Ikon Custom Emoji akan langsung tampil di tombol menu bawah "
                "(tidak dobel dengan karakter placeholder lagi)._"
            )
        await update.message.reply_text(
            f"✅ <b>Emoji berhasil disimpan ke database!</b> ({matched} entri diperbarui){preview_block}{realtime_note}{premium_note}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [mkbtn("a_custom_emoji", "Custom Emoji", callback_data="admin_custom_emoji", style="primary")],
                [mkbtn("a_admin_pnl", "Admin Panel", callback_data="admin_back", style="success")],
            ])
        )
        if category == "button":
            # Tombol menu bawah (reply keyboard) hanya berubah tampilannya kalau
            # bot mengirim ULANG keyboard-nya (batasan API Telegram) — jadi kirim
            # langsung sekarang supaya admin LANGSUNG lihat perubahannya secara real.
            await send_bottom_menu(context, update.effective_chat.id, uid)
        return

    # ─── Custom Emoji: per-slot (Template & Premium) — menangkap custom_emoji_id asli ───
    if state == "admin_set_emoji_slot" and (sess["is_admin"] or is_admin(uid)):
        sess["state"] = None
        data = sess.get("data") or {}
        category, slot = data.get("cat"), data.get("slot")
        if not category or not slot:
            await update.message.reply_text(
                "❌ Sesi tidak valid, coba lagi dari menu Custom Emoji.",
                reply_markup=InlineKeyboardMarkup([[
                    mkbtn("a_custom_emoji", "Custom Emoji", callback_data="admin_custom_emoji", style="primary")
                ]])
            )
            return
        # Deteksi input emoji — tiga cara yang didukung:
        # 1. Tempel Custom Emoji Telegram Premium → entity custom_emoji dari Telegram
        # 2. Ketik ID emoji langsung (angka ≥ 10 digit)
        # 3. Emoji unicode biasa diketik
        #
        # Pakai _extract_custom_emojis() supaya ekstraksi karakter pakai UTF-16
        # slicing yang benar (bukan Python code-point slicing yang bisa salah).
        custom_id  = None
        emoji_char = None
        input_mode = "unicode"

        # Prioritas 1: tempel Custom Emoji Premium → dapat entity dari Telegram
        customs = _extract_custom_emojis(update.message)
        if customs:
            first  = customs[0]
            emoji_char = first["char"]
            custom_id  = first["id"]
            input_mode = "premium_pasted"

        # Prioritas 2: teks adalah angka panjang → ID emoji diketik manual
        if not custom_id and _is_emoji_id(text.strip()):
            custom_id  = text.strip()
            emoji_char = "✨"   # placeholder; <tg-emoji> akan tampilkan desain asli
            input_mode = "id_typed"

        # Prioritas 3: emoji unicode biasa
        if not emoji_char:
            stripped_text = text.strip()
            if stripped_text:
                emoji_char = stripped_text[:20]   # ambil maks 20 char
                input_mode = "unicode"

        if not emoji_char:
            await update.message.reply_text(
                "❌ Tidak ada emoji terdeteksi.\n\n"
                "Kirim salah satu:\n"
                "• Emoji unicode (mis. 🔥)\n"
                "• Tempel Custom Emoji Telegram Premium\n"
                "• ID emoji langsung (angka, mis. <code>5368324170671202286</code>)",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    mkbtn("admin_back", "Kembali", callback_data="admin_custom_emoji", style="primary")
                ]])
            )
            return

        emoji_db_set(category, slot, emoji_char, custom_id, uid)
        emoji_settings = emoji_db_load_all()
        _apply_emoji_overrides()

        if input_mode == "premium_pasted":
            note = (
                f"\n🆔 _Custom Emoji Premium tersimpan (ID: `{custom_id}`) — "
                "desain asli akan terlihat oleh SEMUA user via_ <code><tg-emoji></code>.\n"
                "⚠️ _Catatan: tampil desain asli HANYA jika akun owner bot ini punya "
                "Telegram Premium aktif (atau username Fragment). Kalau belum, otomatis "
                "fallback ke emoji biasa/✨ — bukan bug._"
            )
        elif input_mode == "id_typed":
            note = (
                f"\n🆔 _Emoji ID `{custom_id}` disimpan — "
                "semua user (free & premium) melihat desain aslinya via_ <code><tg-emoji></code>.\n"
                "⚠️ _Catatan: tampil desain asli HANYA jika akun owner bot ini punya "
                "Telegram Premium aktif (atau username Fragment). Kalau belum, otomatis "
                "fallback ke emoji biasa/✨ — bukan bug._"
            )
        else:
            note = ""

        await update.message.reply_text(
            f"✅ <b>Slot</b> `{slot}` <b>tersimpan!</b>{note}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [mkbtn("a_custom_emoji", "Custom Emoji", callback_data="admin_custom_emoji", style="primary")],
                [mkbtn("a_admin_pnl", "Admin Panel", callback_data="admin_back", style="success")],
            ])
        )
        return

    if state == "w_amount":
        try:
            amount = float(text)
            e      = get_user_earnings(uid)
            method = (sess.get("data") or {}).get("method", "bKash")

            if amount < settings["minWithdraw"]:
                return await update.message.reply_text(f"❌ Minimum {settings['minWithdraw']} USD")
            if amount > e["balance"]:
                return await update.message.reply_text("❌ Insufficient balance!")

            sess["state"] = "w_account"
            sess["data"]  = {"method": method, "amount": amount}
            icon = "🟣" if method == "bKash" else "🟠"
            await update.message.reply_text(
                f"{icon} <b>{method} — {amount:.2f} USD</b>\n\n📱 Your {method} number:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[mkbtn("w_cancel", "Cancel", callback_data="w_cancel", style="danger")]])
            )
        except:
            pass
        return

# ─── Withdraw Confirm ───
async def cb_withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    if sess.get("state") != "w_confirm":
        return

    data    = sess.get("data", {})
    method  = data.get("method")
    account = data.get("account")
    amount  = data.get("amount")
    e       = get_user_earnings(uid)

    if amount > e["balance"]:
        sess["state"] = None
        return await query.edit_message_text("❌ Balance changed. Please try again.", parse_mode="HTML")

    e["balance"] = round(e["balance"] - amount, 2)
    await async_save_earnings()

    wid = str(int(time.time() * 1000))
    withdrawals.append({
        "id": wid, "userId": uid,
        "userName": update.effective_user.first_name or "User",
        "userUsername": update.effective_user.username or "",
        "amount": amount, "method": method, "account": account,
        "status": "pending", "requestedAt": now_wib().isoformat(), "processedAt": None
    })
    await async_save_withdrawals()
    sess["state"] = None
    sess["data"]  = None

    await query.edit_message_text(
        f"✅ <b>Withdrawal Request Submitted!</b>\n\n"
        f"💳 {method}\n📱 `{account}`\n💵 {amount:.2f} USD\n\n"
        f"⏳ Admin approval pending.",
        parse_mode="HTML"
    )

# ─── OTP Group Message Handler ───
# ═══════════════════════════════════════════════
# ─── Live Timeline (Twitter-style — OTP baru muncul otomatis, tanpa refresh) ───
# ═══════════════════════════════════════════════
LIVE_TIMELINE_MAX_ITEMS = 15     # jumlah OTP terakhir yang ditampilkan di feed
otp_timeline_global     = []     # rolling feed semua OTP (terbaru di index 0)
live_admin_subscribers  = {}     # { admin_uid(str): {"chat_id": int, "message_id": int} }
live_user_subscribers   = {}     # { user_uid(str):  {"chat_id": int, "message_id": int} }

def _timeline_fmt_item(ev: dict) -> str:
    # PENTING: lookup emoji LEWAT get_svc_icon_html()/get_country_flag_html()
    # saat render (bukan pakai ev['icon']/ev['cc_flag'] yang di-snapshot mentah
    # saat OTP masuk) — supaya Custom Emoji Premium tetap tampil walau admin
    # baru mengubah/menambah emoji SETELAH event ini tercatat, dan supaya
    # konsisten dengan bagian lain bot. Backtick(`)/underscore(_) sebelumnya
    # dipakai di sini padahal parse_mode-nya HTML (itu sintaks Markdown, jadi
    # sebelumnya tampil literal, bukan code/italic) — diganti ke <code>/<i>.
    otp_part = f" — <code>{html.escape(str(ev['otp']))}</code>" if ev.get("otp") else ""
    num_part = f"<code>+{html.escape(str(ev['number']))}</code>" if ev.get("number") else "<code>?</code>"
    icon = get_svc_icon_html(ev.get("svc", "")) if ev.get("svc") else html.escape(ev.get("icon", "📱"))
    flag = get_country_flag_html(ev.get("cc", "")) if ev.get("cc") else html.escape(ev.get("cc_flag", "🌍"))
    return f"{icon} <b>{html.escape(str(ev.get('svc_name','Service')))}</b> {flag} {num_part}{otp_part}  <i>{html.escape(str(ev.get('time_str','')))}</i>"

def _build_admin_timeline_text() -> str:
    items = otp_timeline_global[:LIVE_TIMELINE_MAX_ITEMS]
    header = f"📡 <b>Live OTP Timeline</b> <i>(real-time, tidak perlu refresh)</i>\n\n"
    if not items:
        return header + "<i>Menunggu OTP masuk...</i>"
    body = "\n".join(_timeline_fmt_item(ev) for ev in items)
    return header + body + f"\n\n<i>Update terakhir: {now_wib().strftime('%H:%M:%S')}</i>"

def _build_user_timeline_text(uid: str) -> str:
    items = [ev for ev in otp_timeline_global if str(ev.get("userId")) == str(uid)][:LIVE_TIMELINE_MAX_ITEMS]
    header = "📡 <b>OTP Timeline Kamu</b> <i>(real-time, tidak perlu refresh)</i>\n\n"
    if not items:
        return header + "<i>Belum ada OTP masuk. Begitu OTP datang ke nomor kamu, pesan ini otomatis ter-update.</i>"
    body = "\n".join(_timeline_fmt_item(ev) for ev in items)
    return header + body + f"\n\n<i>Update terakhir: {now_wib().strftime('%H:%M:%S')}</i>"

def _live_timeline_admin_keyboard():
    return InlineKeyboardMarkup([
        [mkbtn("a_live_stop", "Stop Live", callback_data="admin_livetimeline_stop", style="danger")],
        [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
    ])

def _live_timeline_user_keyboard():
    return InlineKeyboardMarkup([
        [mkbtn("cancel", "Stop Live", callback_data="livetimeline_stop", style="danger")],
    ])

async def record_otp_event(source: str, uid, cc: str, svc_id: str, number: str, otp_code: str):
    """Dipanggil setiap kali ada OTP masuk (dari grup Telegram, HTTP webhook, atau panel scraping).
    Menyimpan ke feed global lalu langsung push-update ke semua yang sedang 'live' — tanpa mereka perlu refresh."""
    svc     = services.get(svc_id, {"icon": "📱", "name": svc_id or "Service"})
    country = countries.get(cc, {"flag": "🌍", "name": cc})

    ev = {
        "source": source, "userId": str(uid) if uid else None, "cc": cc, "svc": svc_id,
        "icon": svc.get("icon", "📱"), "svc_name": svc.get("name", svc_id or "Service"),
        "cc_flag": country.get("flag", "🌍"),
        "number": number or "", "otp": otp_code or "",
        "time_str": now_wib().strftime("%H:%M:%S"),
    }
    otp_timeline_global.insert(0, ev)
    del otp_timeline_global[LIVE_TIMELINE_MAX_ITEMS * 3:]  # simpan sedikit buffer ekstra, jaga memory

    app = _tg_app
    if not app:
        return

    # ── Push ke semua admin yang sedang buka Live Timeline ──
    for admin_uid, info in list(live_admin_subscribers.items()):
        try:
            await safe_bot_edit_message_text(
                app.bot, info["chat_id"], info["message_id"],
                _build_admin_timeline_text(), parse_mode="HTML",
                reply_markup=_live_timeline_admin_keyboard()
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.error(f"live timeline (admin) update error uid={admin_uid}: {e}")
                live_admin_subscribers.pop(admin_uid, None)

    # ── Push ke user pemilik OTP ini, kalau dia sedang buka Live Timeline miliknya ──
    if uid:
        sub = live_user_subscribers.get(str(uid))
        if sub:
            try:
                await safe_bot_edit_message_text(
                    app.bot, sub["chat_id"], sub["message_id"],
                    _build_user_timeline_text(uid), parse_mode="HTML",
                    reply_markup=_live_timeline_user_keyboard()
                )
            except Exception as e:
                if "not modified" not in str(e).lower():
                    logger.error(f"live timeline (user) update error uid={uid}: {e}")
                    live_user_subscribers.pop(str(uid), None)

async def handle_user_live_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_feature_enabled("livetimeline"):
        return await update.effective_message.reply_text(feature_disabled_text("Live Timeline"), parse_mode="HTML")
    if not await ensure_verified(update, context):
        return
    uid = str(update.effective_user.id)
    try:
        msg = await update.effective_message.reply_text(
            _build_user_timeline_text(uid), parse_mode="HTML",
            reply_markup=_live_timeline_user_keyboard()
        )
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        msg = await update.effective_message.reply_text(
            _strip_tg_emoji_tags(_build_user_timeline_text(uid)), parse_mode="HTML",
            reply_markup=_live_timeline_user_keyboard()
        )
    live_user_subscribers[uid] = {"chat_id": msg.chat_id, "message_id": msg.message_id}

async def cb_livetimeline_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏹️ Live timeline dihentikan")
    uid = str(update.effective_user.id)
    live_user_subscribers.pop(uid, None)
    try:
        await query.edit_message_text(
            "⏹️ <b>Live Timeline dihentikan.</b>\n\nBuka lagi kapan saja dari menu 📡 Live Timeline.",
            parse_mode="HTML"
        )
    except Exception:
        pass

async def cb_admin_live_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    try:
        msg = await query.message.reply_text(
            _build_admin_timeline_text(), parse_mode="HTML",
            reply_markup=_live_timeline_admin_keyboard()
        )
    except Exception as e:
        if not _is_emoji_related_error(e):
            raise
        msg = await query.message.reply_text(
            _strip_tg_emoji_tags(_build_admin_timeline_text()), parse_mode="HTML",
            reply_markup=_live_timeline_admin_keyboard()
        )
    live_admin_subscribers[uid] = {"chat_id": msg.chat_id, "message_id": msg.message_id}

async def cb_admin_live_timeline_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏹️ Live timeline dihentikan")
    uid = str(update.effective_user.id)
    live_admin_subscribers.pop(uid, None)
    try:
        await query.edit_message_text("⏹️ <b>Live Timeline dihentikan.</b>", parse_mode="HTML")
    except Exception:
        pass

# ─── Main Menu (Reply keyboard bawah, berwarna) shared handler map ───
MENU_HANDLERS = {
    "getnumber":   handle_get_numbers,
    "getfile":     handle_get_file,
    "cariotp":     handle_cari_otp_menu,
    "livetraffic": handle_live_traffic,
    "tools":       handle_tools,
    "profil":      handle_profil,
    "support":     handle_support,
    "minimizemenu":handle_minimize_menu,
}

# Label tombol reply keyboard bawah -> action key di MENU_HANDLERS.
# Dibangun ULANG setiap kali dipanggil (bukan dict statis) dari
# MAIN_MENU_BUTTON_SPECS, supaya SELALU cocok dengan teks tombol yang benar-
# benar sedang ditampilkan ke user — baik dalam bahasa EN maupun ID, dan
# dengan emoji TERBARU hasil kustomisasi admin di menu Custom Emoji. Kalau
# admin mengganti emoji tombol, deteksi tombol yang ditekan otomatis ikut
# berubah tanpa perlu restart bot.
def reply_menu_labels() -> dict:
    mapping = {}
    for tr_key, emoji_key, emoji_default, action in MAIN_MENU_BUTTON_SPECS:
        for lang_dict in TRANSLATIONS.values():
            text = lang_dict.get(tr_key)
            if text:
                mapping[_menu_label_text(text, emoji_key, emoji_default)] = action
    return mapping

async def handle_otp_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.message.chat_id
    if str(chat_id) != str(OTP_GROUP_ID) and chat_id != OTP_GROUP_ID:
        return

    msg_text = update.message.text or update.message.caption or ""
    msg_id   = update.message.message_id
    if not msg_text:
        return

    # ── Backlog guard: abaikan pesan OTP yang lebih tua dari 5 menit ──
    # (mis. antrian pesan lama yang baru terkirim saat bot restart/start)
    msg_time = update.message.date
    if msg_time:
        age = datetime.now(timezone.utc) - msg_time
        if age > timedelta(minutes=OTP_MAX_AGE_MINUTES):
            logger.info(f"⏭️ OTP msg [{msg_id}] diabaikan, terlalu lama ({age}, batas {OTP_MAX_AGE_MINUTES} menit)")
            return

    logger.info(f"📨 OTP Group [{msg_id}]: {msg_text[:120]}")
    logger.info(f"🔍 Active numbers count: {len(active_numbers)}")
    matched = find_matching_active_number(msg_text)
    if not matched:
        logger.warning(f"⚠️ No active number matched for msg: {msg_text[:200]}")
        return

    data = active_numbers[matched]
    uid  = data["userId"]
    cc   = data.get("countryCode", "")

    # Nomor ini cuma dianggap AKTIF kalau masih ada di daftar yang sedang
    # ditampilkan ke user (menu Get Number-nya). Kalau tidak — mis. user sudah
    # klik "Get New Number", ganti service/negara, atau bot baru restart
    # (sesi lama otomatis kosong) — anggap sudah tidak aktif: jangan kirim
    # OTP-nya dan bersihkan dari active_numbers.
    if not _number_still_assigned(uid, matched):
        logger.info(f"⏭️ OTP untuk +{matched} diabaikan — nomor sudah tidak ada di daftar aktif user {uid}.")
        active_numbers.pop(matched, None)
        rebuild_suffix_index()
        await async_save_active()
        return

    if data.get("lastOTP") == msg_id:
        return
    data["lastOTP"] = msg_id
    data["otpCount"] = data.get("otpCount", 0) + 1
    await async_save_active()

    otp_code = extract_otp(msg_text)
    if _is_duplicate_otp(matched, otp_code):
        logger.info(f"⏭️ OTP {otp_code} untuk +{matched} dobel dalam {OTP_DUPLICATE_WINDOW_SECONDS} detik terakhir, dilewati.")
        return
    earned   = await add_earning(uid, cc)
    balance  = get_user_earnings(uid)["balance"]
    svc_id_  = data.get("service", "")
    svc      = services.get(svc_id_, {"icon": "📱", "name": "Service"})
    country  = countries.get(cc, {"flag": "🌍", "name": cc})

    asyncio.create_task(record_otp_event("group", uid, cc, data.get("service"), matched, otp_code))

    # ── PENTING: pakai get_svc_icon_html()/get_country_flag_html() (bukan
    # svc['icon']/country['flag'] mentah) supaya Custom Emoji Premium yang
    # diatur admin tampil lewat tag <tg-emoji> asli untuk SEMUA user. Flag
    # negara mentah (unicode regional-indicator) sering TIDAK ter-render di
    # banyak device/client Telegram (mis. Windows Desktop) dan otomatis jatuh
    # ke placeholder bulat/globe — makanya sebelumnya flag selalu tampil
    # sebagai globe di notifikasi ini walau custom emoji sudah diatur.
    notify = (
        f"📨 <b>OTP Received!</b>\n\n"
        f"{get_svc_icon_html(svc_id_)} <b>Service:</b> {html.escape(str(svc.get('name','Service')))}\n"
        f"{get_country_flag_html(cc)} <b>Country:</b> {html.escape(str(country.get('name', cc)))}\n"
        f"📞 <b>Number:</b> <code>+{html.escape(str(matched))}</code>\n"
    )
    if otp_code:
        notify += f"\n🔑 <b>OTP Code:</b> <code>{html.escape(str(otp_code))}</code>\n"
    notify += f"\n💵 <b>+{earned:.2f} USD earned!</b>\n💰 <b>Balance: {balance:.2f} USD</b>"

    try:
        sent_notify = await safe_send_message(context.bot, uid, notify, parse_mode="HTML")
        sent_fwd    = await context.bot.forward_message(uid, OTP_GROUP_ID, msg_id)
        await _track_otp_notify_msg(matched, sent_notify.message_id)
        await _track_otp_notify_msg(matched, sent_fwd.message_id)
    except Exception as e:
        logger.error(f"OTP notify error: {e}")

    # Auto-Delete OTP (kalau di-ON admin): hapus pesan OTP mentah di Grup OTP
    # setelah durasi yang diatur — pesan DM ke user TIDAK ikut dihapus.
    schedule_auto_delete_ids(context, chat_id, msg_id)

    otp_log.append({
        "phoneNumber": matched, "userId": uid, "countryCode": cc,
        "service": data.get("service"), "otpCode": otp_code, "earned": earned,
        "messageId": msg_id, "delivered": True,
        "timestamp": now_wib().isoformat()
    })
    await async_save_otp_log()

# ─── Real-time Group Member Change Handler ───
REQUIRED_GROUP_IDS = {MAIN_CHANNEL_ID, CHAT_GROUP_ID, OTP_GROUP_ID}

async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কেউ group ছাড়লে বা join করলে real-time এ handle করো"""
    try:
        cm = update.chat_member
        if not cm:
            return

        chat_id = cm.chat.id
        if chat_id not in REQUIRED_GROUP_IDS:
            return

        user    = cm.new_chat_member.user
        uid     = str(user.id)
        old_status = cm.old_chat_member.status  # আগের status
        new_status = cm.new_chat_member.status  # নতুন status

        LEFT_STATUSES   = {"left", "kicked", "banned"}
        JOINED_STATUSES = {"member", "administrator", "creator"}

        # ── কেউ group ছেড়ে গেলে ──
        if old_status in JOINED_STATUSES and new_status in LEFT_STATUSES:
            logger.info(f"👋 User {uid} left chat {chat_id}")

            if uid not in users:
                return

            # verified=False করো — referral ছাড়া user হলেও
            users[uid]["verified"] = False
            sess = get_session(uid)
            sess["verified"] = False

            # referral ছিল এবং confirmed ছিল → count কমাও
            if users[uid].get("referralVerified", False):
                users[uid]["referralVerified"] = False
                referrer_id = users[uid].get("referredBy")
                if referrer_id and referrer_id in users:
                    users[referrer_id]["referralCount"] = max(0, users[referrer_id].get("referralCount", 0) - 1)
                    if referrer_id in referrals and uid in referrals[referrer_id]:
                        referrals[referrer_id].remove(uid)
                    await async_save_referrals()
                    logger.info(f"📉 Referral removed: uid={uid} left → referrer={referrer_id} count={users[referrer_id]['referralCount']}")
                    try:
                        await context.bot.send_message(
                            int(referrer_id),
                            f"⚠️ <b>Referral Lost!</b>\n\n"
                            f"One of your referred users has left the group.\n"
                            f"👥 Current Referrals: <b>{users[referrer_id]['referralCount']}</b>",
                            parse_mode="HTML"
                        )
                    except:
                        pass

            await async_save_users()
            logger.info(f"🔒 Access revoked for uid={uid} (left chat {chat_id})")

        # ── কেউ আবার group এ join করলে — শুধু log করো, verify এ count হবে ──
        elif old_status in LEFT_STATUSES and new_status in JOINED_STATUSES:
            logger.info(f"✅ User {uid} joined chat {chat_id}")

    except Exception as e:
        logger.error(f"handle_chat_member_update error: {e}")

# ─── /cancel command ───
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    sess = get_session(uid)
    sess["state"] = None
    sess["data"]  = None
    if is_admin(uid):
        sess["is_admin"] = True
    await update.message.reply_text("✅ Cancelled.")
    await send_bottom_menu(context, update.effective_chat.id, uid)

# ─── Periodic scheduled check ───
async def scheduled_membership_check(app):
    while True:
        await asyncio.sleep(30 * 60)  # ৩০ মিনিট পর পর background check
        if not settings.get("requireVerification", True):
            continue
        logger.info(f"🔄 [Scheduled] Checking {len(users)} users...")
        blocked = 0
        for uid, user in list(users.items()):
            try:
                membership = await check_membership(int(uid), app)
                if not membership["allJoined"]:
                    users[uid]["verified"] = False
                    blocked += 1
                    sess = get_session(uid)
                    sess["verified"] = False

                    # ── রেফার কাউন্ট কমাও যদি আগে verified ছিল ──
                    if users[uid].get("referralVerified", False):
                        users[uid]["referralVerified"] = False
                        referrer_id = users[uid].get("referredBy")
                        if referrer_id and referrer_id in users:
                            current_count = users[referrer_id].get("referralCount", 0)
                            users[referrer_id]["referralCount"] = max(0, current_count - 1)
                            # referrals list থেকেও সরাও
                            if referrer_id in referrals and uid in referrals[referrer_id]:
                                referrals[referrer_id].remove(uid)
                            await async_save_referrals()
                            logger.info(f"📉 Referral removed: uid={uid} left group → referrer={referrer_id} count={users[referrer_id]['referralCount']}")
                            try:
                                await app.bot.send_message(
                                    int(referrer_id),
                                    f"⚠️ <b>Referral Lost!</b>\n\n"
                                    f"One of your referred users has left the group.\n"
                                    f"👥 Current Referrals: <b>{users[referrer_id]['referralCount']}</b>",
                                    parse_mode="HTML"
                                )
                            except:
                                pass

                    try:
                        pass
                    except:
                        pass
                else:
                    users[uid]["verified"] = True
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Scheduled check error for {uid}: {e}")
        await async_save_users()
        logger.info(f"✅ [Scheduled] {blocked} users blocked.")

# ═══════════════════════════════════════════════
# ═══════════════════════════════════════════════
# ─── OTP Panel Scraping System (multi-panel engine v2) ───
#     Powered by panel_fetchers.py — supports:
#     INTS, IMS, Konekta, Standard, ProofSMS,
#     RoxySMS, VoiceGate, NumberPanel, TimeSMS, SniperPanel, XMS, Falcon SMS,
#     Porsha SMS, NEXA SMS
# ═══════════════════════════════════════════════

PANEL_SETTINGS_FILE  = os.path.join(DATA_DIR, "panel_settings.json")

# ── SQLite storage untuk Panels & Accounts (persis skema SC_jadi/otp_bot.db) ──
PANEL_DB_FILE = os.path.join(DATA_DIR, "otp_bot.db")

def db_conn():
    c = sqlite3.connect(PANEL_DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def db_init():
    with db_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS panels (
            name       TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            ptype      TEXT NOT NULL,
            fp         TEXT DEFAULT NULL,
            enabled    INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_name TEXT NOT NULL,
            username   TEXT NOT NULL,
            password   TEXT NOT NULL,
            poll_interval INTEGER DEFAULT NULL,
            webhook_url TEXT DEFAULT NULL,
            webhook_secret TEXT DEFAULT NULL,
            active     INTEGER DEFAULT 1,
            FOREIGN KEY(panel_name) REFERENCES panels(name) ON DELETE CASCADE
        );
        """)
        account_columns = {
            row["name"] for row in c.execute("PRAGMA table_info(accounts)").fetchall()
        }
        if "poll_interval" not in account_columns:
            # Existing deployments keep working and use the panel-type
            # default until an interval is set for the account.
            c.execute("ALTER TABLE accounts ADD COLUMN poll_interval INTEGER DEFAULT NULL")
        if "webhook_url" not in account_columns:
            c.execute("ALTER TABLE accounts ADD COLUMN webhook_url TEXT DEFAULT NULL")
        if "webhook_secret" not in account_columns:
            c.execute("ALTER TABLE accounts ADD COLUMN webhook_secret TEXT DEFAULT NULL")

db_init()

def get_panels() -> list:
    with db_conn() as c:
        return c.execute("SELECT * FROM panels ORDER BY name").fetchall()

def get_panel(name: str):
    with db_conn() as c:
        return c.execute("SELECT * FROM panels WHERE name=?", (name,)).fetchone()

def get_accounts(panel_name: str) -> list:
    """Hanya akun aktif (active=1) — dipakai untuk start_panel."""
    with db_conn() as c:
        return c.execute(
            "SELECT * FROM accounts WHERE panel_name=? AND active=1", (panel_name,)
        ).fetchall()

def get_all_accounts(panel_name: str) -> list:
    with db_conn() as c:
        return c.execute("SELECT * FROM accounts WHERE panel_name=?", (panel_name,)).fetchall()

# ── Migrasi otomatis dari panels.json lama (jika ada, dari deployment sebelumnya) ──
def _migrate_legacy_panels_json():
    legacy_file = os.path.join(DATA_DIR, "panels.json")
    if not os.path.exists(legacy_file):
        return
    try:
        legacy = load_json(legacy_file, [])
        if not legacy:
            return
        with db_conn() as c:
            already = c.execute("SELECT COUNT(*) n FROM panels").fetchone()["n"]
        if already > 0:
            return  # sudah ada data di DB, jangan timpa
        with db_conn() as c:
            for p in legacy:
                name = p.get("name") or p.get("url") or "Panel"
                c.execute(
                    "INSERT OR IGNORE INTO panels(name,url,ptype,fp,enabled) VALUES(?,?,?,?,1)",
                    (name, p.get("url", ""), p.get("type", "ints"), p.get("fp"))
                )
                if p.get("username"):
                    c.execute(
                        "INSERT INTO accounts(panel_name,username,password,poll_interval) "
                        "VALUES(?,?,?,?)",
                        (name, p["username"], p.get("password", ""), p.get("poll_interval"))
                    )
        logger.info(f"📦 Migrated {len(legacy)} legacy panel(s) from panels.json → otp_bot.db")
        os.rename(legacy_file, legacy_file + ".migrated")
    except Exception as e:
        logger.error(f"Legacy panel migration error: {e}")

_migrate_legacy_panels_json()

def _migrate_legacy_rez_sms_panel():
    """Alihkan built-in REZ SMS lama dari engine INTS ke API CDR."""
    with db_conn() as c:
        row = c.execute(
            "SELECT name, url, ptype FROM panels WHERE lower(name)=?", ("rez sms",)
        ).fetchone()
        if not row:
            return
        if row["ptype"] == "rez_sms" and row["url"] == "https://rezsms.org/api/cdr.php":
            return
        c.execute(
            "UPDATE panels SET url=?, ptype=? WHERE name=?",
            ("https://rezsms.org/api/cdr.php", "rez_sms", row["name"]),
        )
        logger.warning(
            f"🔄 Migrated [{row['name']}] to Rez SMS API; "
            "existing account entries may need to be replaced with API tokens."
        )

_migrate_legacy_rez_sms_panel()

otp_panel_tasks   = {}   # { account_id: asyncio.Task }
otp_panel_status  = {}   # { account_id: "running" | "stopped" | "error" }
otp_panel_session = {}   # { account_id: session_info } — in-memory only, not persisted
panel_webhook_lock = asyncio.Lock()

# ═══════════════════════════════════════════════
# ─── Alert System: Offline / Login Expired / Saldo Habis / API Error ───
# ═══════════════════════════════════════════════
OTP_ALERT_COOLDOWN_MINUTES = 30   # jangan spam alert yang sama dalam rentang ini
otp_panel_last_alert = {}         # { "panel:akun:jenis": last_sent_unix_time }

ALERT_LABELS = {
    "offline": ("🔴", "Panel Offline"),
    "login":   ("🔑", "Login Expired / Gagal Login"),
    "saldo":   ("💸", "Saldo Panel Habis"),
    "api":     ("⚠️", "API Error"),
}

def _classify_panel_error(msg: str) -> str:
    """Tebak jenis error dari teks exception panel."""
    m = (msg or "").lower()
    if any(k in m for k in [
        "saldo", "balance", "insufficient", "credit", "kredit",
        "top up", "topup", "no fund", "out of fund", "add fund",
    ]):
        return "saldo"
    if any(k in m for k in [
        "timeout", "timed out", "connection", "connect", "refused",
        "unreachable", "resolve", "name or service not known",
        "network", "max retries exceeded", "temporary failure",
    ]):
        return "offline"
    if any(k in m for k in [
        "unauthorized", "401", "403", "invalid credential",
        "login gagal", "login failed", "auth", "forbidden", "captcha",
    ]):
        return "login"
    return "api"

async def alert_owner_panel(app, bn: str, username: str, alert_type: str, detail: str = ""):
    """Kirim notifikasi ke semua owner/admin, dengan cooldown supaya tidak spam."""
    now = time.time()
    key = f"{bn}:{username}:{alert_type}"
    last = otp_panel_last_alert.get(key, 0)
    if now - last < OTP_ALERT_COOLDOWN_MINUTES * 60:
        return
    otp_panel_last_alert[key] = now

    icon, label = ALERT_LABELS.get(alert_type, ("⚠️", "Panel Error"))
    text = (
        f"{icon} <b>ALERT: {label}</b>\n\n"
        f"📡 <b>Panel:</b> {bn}\n"
        f"👤 <b>Akun:</b> `{username}`\n"
        f"🕐 <b>Waktu:</b> {now_wib().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    if detail:
        text += f"\n\n📝 <b>Detail:</b> `{detail[:300]}`"

    if not admins:
        logger.warning(f"⚠️ Alert '{alert_type}' untuk [{bn}] {username} tidak terkirim — belum ada admin/owner login.")
        return

    for admin_uid in list(admins):
        try:
            await app.bot.send_message(int(admin_uid), text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"alert_owner_panel send error uid={admin_uid}: {e}")

async def alert_owner_panel_recovered(app, bn: str, username: str):
    """Kirim notifikasi saat panel yang tadinya error sudah normal lagi."""
    text = (
        f"✅ <b>Panel Kembali Normal</b>\n\n"
        f"📡 <b>Panel:</b> {bn}\n"
        f"👤 <b>Akun:</b> `{username}`\n"
        f"🕐 <b>Waktu:</b> {now_wib().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    for admin_uid in list(admins):
        try:
            await app.bot.send_message(int(admin_uid), text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"alert_owner_panel_recovered send error uid={admin_uid}: {e}")
    # reset cooldown supaya error berikutnya langsung dikirim ulang
    for k in list(otp_panel_last_alert.keys()):
        if k.startswith(f"{bn}:{username}:"):
            otp_panel_last_alert.pop(k, None)

PANEL_TOKEN_TYPES = {
    "thirdwave", "elite_sms", "elite_sms_api", "elite_sms_v1", "rez_sms", "axon", "smsnode", "mjsms_api",
    "augestel", "ksi", "xisora", "mbcs_api",
}

def _panel_uses_api_token(ptype: str) -> bool:
    return str(ptype or "").strip().lower() in PANEL_TOKEN_TYPES

PANEL_TYPES = ["ints", "ims", "konekta", "standard", "purplesms", "proofsms",
               "roxy", "voicegate", "numberpanel", "timesms", "sniper",
               "xms", "zonesms", "zedsms", "sms", "falcon", "porsha",
               "nexa", "aleius", "mjsms", "mjsms_api", "thirdwave", "elite_sms",
               "elite_sms_api", "elite_sms_v1",
               "rez_sms", "axon", "smsnode", "augestel", "ksi", "gren_sms", "xisora",
               "mbcs", "mbcs_api"]

PANEL_TYPE_LABEL = {
    "ints":        "INTS (HADI/Seven1Tel/Wolf/Gaza/MAIT)",
    "ims":         "IMS Panel",
    "konekta":     "Konekta",
    "standard":    "Standard (TrueSMS/compatible)",
    "purplesms":   "Purple SMS",
    "proofsms":    "ProofSMS",
    "roxy":        "RoxySMS",
    "voicegate":   "VoiceGate",
    "numberpanel": "NumberPanel",
    "timesms":     "TimeSMS",
    "sniper":      "SniperPanel",
    "xms":         "XMS (Django incoming messages)",
    "zonesms":     "Zone SMS (/subclient/Reports)",
    "zedsms":      "Zed SMS (ZEDSMS API)",
    "sms":         "SMS (Generic)",
    "falcon":      "Falcon SMS",
    "porsha":      "Porsha SMS (/messages HTML inbox)",
    "nexa":        "NEXA SMS (/sms-cdr-reports HTML inbox)",
    "aleius":      "Aleius SMS (/agent/cdr → /client/cdr HTML inbox)",
    "mjsms":       "MJ SMS (/sms-records HTML inbox)",
    "mjsms_api":   "MJ SMS API (Agent API)",
    "thirdwave":   "ThirdWave (Bearer API)",
    "elite_sms":   "IPRN Elite (JSON-RPC API)",
    "elite_sms_api": "Elite SMS (REST API + Webhook)",
    "elite_sms_v1": "Elite SMS v1 (Dashboard Login)",
    "rez_sms":     "Rez SMS (CDR API)",
    "axon":        "Axon (Bearer API)",
    "smsnode":     "SMSNode (X-API-Key)",
    "augestel":    "Augestel (Bearer API + Webhook)",
    "ksi":         "KSI (Bearer API + Webhook)",
    "gren_sms":    "Gren SMS (Django incoming messages)",
    "xisora":      "Xisora (MDR API)",
    "mbcs":        "MBCs (MBC SMS /agent/SMSCDRReports)",
    "mbcs_api":   "MBCs Api (MBC PANL)",
}

# Beberapa panel type di-dispatch berdasarkan "brand name" tetap
# (mengikuti convention panel_fetchers.py's new_panel_login/new_panel_fetch)
_BN_FOR_TYPE = {
    "roxy": "RoxySMS", "voicegate": "VoiceGate",
    "numberpanel": "NumberPanel", "sniper": "SniperPanel",
}

# ── Daftar panel bawaan (built-in) — sama persis seperti SC_jadi ──
BUILTIN_PANELS = {
    "ChoiceSMS":    {"url": "http://51.77.52.79/ints",          "ptype": "ints"},
    "FlynSMS":      {"url": "http://91.232.105.47/ints",        "ptype": "ints"},
    "Gaza SMS":     {"url": "http://144.217.71.192/ints",       "ptype": "ints", "fp": "agent"},
    "GoatPanel":    {"url": "http://167.114.117.67/ints",       "ptype": "ints"},
    "HADI_SMS":     {"url": "http://2.59.169.96/ints",          "ptype": "ints"},
    "IMS Panel":    {"url": "https://www.imssms.org",           "ptype": "ims"},
    "KmSms":        {"url": "http://54.36.173.235/ints",        "ptype": "ints"},
    "Konekta":      {"url": "https://konektapremium.net",       "ptype": "konekta"},
    "MSI SMS":      {"url": "http://145.239.130.45/ints",       "ptype": "ints"},
    "Number Panel": {"url": "http://51.89.99.105/NumberPanel",  "ptype": "numberpanel"},
    "Proof SMS":    {"url": "http://217.182.195.194/ints",      "ptype": "proofsms"},
    "Purple SMS":   {"url": "http://85.195.94.50/sms",          "ptype": "purplesms"},
    "Roxy SMS":     {"url": "http://www.roxysms.net",           "ptype": "roxy"},
    "Seven1Tel":    {"url": "http://94.23.120.156/ints",        "ptype": "ints"},
    "Shark SMS":    {"url": "http://65.109.111.158/ints",       "ptype": "ints"},
    "True SMS":     {"url": "https://truesms.net",              "ptype": "standard"},
    "VoiceGate":    {"url": "http://139.99.68.183/ints",        "ptype": "ints"},
    "Wolf":         {"url": "http://213.32.24.208/ints",        "ptype": "ints"},
    "NEXA":         {"url": "https://169.58.185.211/ints",      "ptype": "nexa"},
    "MarkOI":       {"url": "http://51.75.144.178/ints",        "ptype": "ints"},
    "Fire SMS":     {"url": "http://54.39.104.241/ints",        "ptype": "ints"},
    "Sniper Panel": {"url": "http://135.125.222.224/ints",      "ptype": "sniper"},
    "MAIT SMS":     {"url": "http://168.119.13.175/ints",       "ptype": "ints", "fp": "agent"},
    "MJ SMS":       {"url": "http://147.93.139.149/ints",       "ptype": "mjsms"},
    "MJ SMS (API)": {"url": "http://147.93.139.149/ints/login/api/agent_sms.php",
                     "ptype": "mjsms_api"},
    "Time SMS":     {"url": "https://www.timesms.org",          "ptype": "timesms"},
    "XMS":          {"url": "http://167.172.67.9",              "ptype": "xms"},
    "Zone SMS":     {"url": "http://zonesms.net",               "ptype": "zonesms"},
    "Zed SMS":      {"url": "http://194.233.79.217",              "ptype": "zedsms"},
    "Nexsor":       {"url": "https://nexor-iprn.com",             "ptype": "sms"},
    "Falcon SMS":  {"url": "http://169.58.94.4/login",          "ptype": "falcon"},
    "porsha":       {"url": "http://143.246.43.163/login",     "ptype": "porsha"},
    "Zento SMS":    {"url": "http://54.38.176.48/ints",         "ptype": "ints"},
    "LAMIX":        {"url": "http://51.210.208.26/ints",        "ptype": "ints"},
    "ZYRON":        {"url": "http://151.80.19.204/ints",        "ptype": "ints"},
    "Aleius":       {"url": "http://169.58.213.56/ints",        "ptype": "aleius"},
    "SOTY SMS":     {"url": "http://45.14.135.150/ints",        "ptype": "ints"},
    "BOLT SMS":     {"url": "http://93.190.143.35/ints",        "ptype": "ints"},
    "FLY SMS":      {"url": "http://193.70.33.154/ints",        "ptype": "ints"},
    "Shadow SMS":   {"url": "http://51.68.35.151/ints",         "ptype": "ints"},
    "ThirdWave":    {"url": "https://clients.thirdwave.im",     "ptype": "thirdwave"},
    "IPRN Elite":   {"url": "https://api.iprn-elite.com/v1.0",  "ptype": "elite_sms"},
    "Elite SMS":    {"url": "https://elite-sms.com/api",        "ptype": "elite_sms_api"},
    "Elite SMS v1": {"url": "https://elite-sms.com",            "ptype": "elite_sms_v1"},
    "REZ SMS":      {"url": "https://rezsms.org/api/cdr.php",   "ptype": "rez_sms"},
    "Axon":         {"url": "https://axonsms.xyz",              "ptype": "axon"},
    "SMSNode":      {"url": "https://smsnode.app/api/v1",       "ptype": "smsnode"},
    "Augestel":     {"url": "https://augestel.com/api/v1/iprn", "ptype": "augestel"},
    "KSI":          {"url": "https://www.ksiiprn.com/api/v1/iprn", "ptype": "ksi"},
    "Gren SMS":     {"url": "http://143.110.245.86",             "ptype": "gren_sms"},
    "Xisora":       {"url": "http://51.38.148.122/crapi/reseller/mdr.php", "ptype": "xisora"},
    "MBCs":        {"url": "https://mbcs-ms.com",                       "ptype": "mbcs"},
    "MBCs Api":   {"url": "https://mbcs-ms.com/crapi/mbc/viewstats",   "ptype": "mbcs_api"},
    "Proton SMS":   {"url": "http://109.236.84.81/ints",        "ptype": "ints"},
    "FLEX SMS":     {"url": "http://168.119.13.175/ints",       "ptype": "ints"},
    "Prime SMS":    {"url": "http://54.36.169.49/ints",         "ptype": "ints"},
    "SQUAD SMS":    {"url": "http://51.77.221.209/ints",        "ptype": "ints"},
    "CORE SMS":     {"url": "http://139.99.68.231/ints",        "ptype": "ints"},
    "IOS SMS":      {"url": "http://139.99.9.120/ints",         "ptype": "ints"},
}

# ── Template default untuk pesan OTP yang dikirim ke grup ──
DEFAULT_OTP_TEMPLATE = {
    "text": (
        "{flag} <b>{country}</b>\n"
        "📞 Number: `+{number_masked}`\n"
        "🏷️ Prefix: {prefix}\n"
        "🔧 Service: {svc_icon} {service}\n"
        "🔑 OTP: `{otp}`\n"
        "💬 _{message}_\n\n"
        "🏷️ Panel: {panel} | ⏰ {time}"
    ),
    "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
}

# ── Template default untuk pesan OTP yang dikirim ke user (chat pribadi) ──
DEFAULT_USER_OTP_TEMPLATE = {
    "text": (
        "📨 <b>OTP Received!</b>\n\n"
        "{svc_icon} <b>Service:</b> {service}\n"
        "{flag} <b>Country:</b> {country}\n"
        "📞 <b>Number:</b> `+{number}`\n"
        "\n🔑 <b>OTP Code:</b> `{otp}`\n"
        "\n💵 <b>+{earned} USD earned!</b>\n"
        "💰 <b>Balance: {balance} USD</b>"
    ),
    "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
}

# ── 3 Preset pilihan template GRUP (admin tinggal pilih, atau custom sendiri) ──
GROUP_TEMPLATE_PRESETS = {
    "1": {
        "name": "Minimalis",
        "text": (
            "{flag} {iso} <b>{country}</b>\n"
            "📞 Number: `+{number_masked}`\n"
            "🏷️ Prefix: {prefix}\n"
            "🔧 Service: {svc_icon} {service}\n"
            "🔑 OTP: `{otp}`\n"
            "💬 _{message}_\n\n"
            "🏷️ Panel: {panel} | ⏰ {time}"
        ),
        "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
    },
    "2": {
        "name": "Detail",
        "text": (
            "━━━━━━━━━━━━━━\n"
            "{flag} {iso} <b>{country}</b> | {svc_icon} <b>{service}</b>\n"
            "━━━━━━━━━━━━━━\n"
            "📞 Number : `+{number_masked}`\n"
            "🏷️ Prefix : {prefix}\n"
            "🔑 OTP    : `{otp}`\n"
            "💬 SMS    : _{message}_\n"
            "🏷️ Panel  : {panel}\n"
            "⏰ Time   : {time}\n"
            "━━━━━━━━━━━━━━"
        ),
        "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
    },
    "3": {
        "name": "Compact",
        "text": (
            "{flag} {iso} {country} • {svc_icon} {service} • +{number_masked}\n"
            "Prefix: {prefix}\n"
            "OTP: `{otp}` — {panel}, {time}"
        ),
        "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
    },
}

# ── 3 Preset pilihan template USER (chat pribadi) ──
USER_TEMPLATE_PRESETS = {
    "1": {
        "name": "Standard",
        "text": (
            "📨 <b>OTP Received!</b>\n\n"
            "{svc_icon} <b>Service:</b> {service}\n"
            "{flag} {iso} <b>Country:</b> {country}\n"
            "📞 <b>Number:</b> `+{number}`\n"
            "\n🔑 <b>OTP Code:</b> `{otp}`\n"
            "\n💵 <b>+{earned} USD earned!</b>\n"
            "💰 <b>Balance: {balance} USD</b>"
        ),
        "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
    },
    "2": {
        "name": "Detail",
        "text": (
            "✅ <b>OTP Berhasil Diterima</b>\n"
            "━━━━━━━━━━━━━━\n"
            "{flag} {iso} Negara   : {country}\n"
            "{svc_icon} Layanan  : {service}\n"
            "📞 Nomor    : `+{number}`\n"
            "🔑 Kode OTP : `{otp}`\n"
            "━━━━━━━━━━━━━━\n"
            "💵 Earned   : +{earned} USD\n"
            "💰 Saldo    : {balance} USD\n"
            "⏰ {time}"
        ),
        "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
    },
    "3": {
        "name": "Simple",
        "text": (
            "🔑 OTP kamu: `{otp}`\n"
            "📞 +{number} ({svc_icon} {service}) — {flag} {iso}\n"
            "💰 Saldo: {balance} USD (+{earned})"
        ),
        "buttons": [{"type": "copy", "label": "📋 Copy OTP", "value": "{otp}", "style": "success"}]
    },
}

def load_panel_settings() -> dict:
    s = load_json(PANEL_SETTINGS_FILE, {})
    if "groups" not in s:
        s["groups"] = []
    if "template" not in s:
        s["template"] = DEFAULT_OTP_TEMPLATE
    return s

def save_panel_settings(s: dict):
    save_json(PANEL_SETTINGS_FILE, s)

def get_otp_groups() -> list:
    return load_panel_settings().get("groups", [])

def add_otp_group(chat_id: str):
    s = load_panel_settings()
    chat_id = str(chat_id)
    if chat_id not in [str(g) for g in s["groups"]]:
        s["groups"].append(chat_id)
        save_panel_settings(s)
    return s["groups"]

def remove_otp_group(chat_id: str):
    s = load_panel_settings()
    chat_id = str(chat_id)
    s["groups"] = [g for g in s["groups"] if str(g) != chat_id]
    save_panel_settings(s)
    return s["groups"]

def get_otp_template() -> dict:
    return load_panel_settings().get("template", DEFAULT_OTP_TEMPLATE)

def set_otp_template(tmpl: dict):
    s = load_panel_settings()
    s["template"] = tmpl
    save_panel_settings(s)

def get_otp_user_template() -> dict:
    return load_panel_settings().get("user_template", DEFAULT_USER_OTP_TEMPLATE)

def set_otp_user_template(tmpl: dict):
    s = load_panel_settings()
    s["user_template"] = tmpl
    save_panel_settings(s)

def _mask_number(num: str) -> str:
    num    = re.sub(r"\D", "", str(num))
    mask   = settings.get("hidden_number_mask", "••••")
    prefix = max(0, int(settings.get("mask_prefix_digits", 4)))
    suffix = max(0, int(settings.get("mask_suffix_digits", 2)))
    total  = len(num)
    if total <= prefix + suffix:
        return num
    front = num[:prefix]
    back  = num[-suffix:] if suffix > 0 else ""
    return front + mask + back

def _mask_number_html(num: str) -> str:
    """Sama seperti _mask_number(), tapi untuk pesan dengan parse_mode="HTML".
    Kalau mask-nya diset pakai Custom Emoji Premium (custom_emoji_id), bagian
    tengah dirender lewat tag <tg-emoji> asli — supaya SEMUA user (gratis
    maupun premium) melihat desain emoji aslinya, bukan cuma placeholder."""
    num    = re.sub(r"\D", "", str(num))
    prefix = max(0, int(settings.get("mask_prefix_digits", 4)))
    suffix = max(0, int(settings.get("mask_suffix_digits", 2)))
    total  = len(num)
    if total <= prefix + suffix:
        return html.escape(num)
    front = html.escape(num[:prefix])
    back  = html.escape(num[-suffix:] if suffix > 0 else "")
    mask_entry = {
        "char": settings.get("hidden_number_mask", "••••"),
        "id":   settings.get("hidden_number_mask_id"),
    }
    mid = emoji_html(mask_entry)
    return front + mid + back

def _prefix_number_html(num: str) -> str:
    """Render the first six digits as a Telegram spoiler.

    The value is intentionally not a button: Telegram's native spoiler
    interaction is the reliable "tap to reveal" behavior inside a message.
    """
    clean = re.sub(r"\D", "", str(num))
    return f"<tg-spoiler>{html.escape(clean[:6])}</tg-spoiler>"

def _md_to_html(s: str) -> str:
    s = re.sub(r'<code>([^</code>\n]+)`', lambda m: f'<code>{html.escape(m.group(1))}</code>', s)
    s = re.sub(r'\<b>([^</b>\n]+)\*', lambda m: f'<b>{html.escape(m.group(1))}</b>', s)
    s = re.sub(r'(?<!\w)<i>([^</i>\n]+)_(?!\w)', lambda m: f'<i>{html.escape(m.group(1))}</i>', s)
    return s


def detect_full_language(text: str, iso: str = "") -> tuple:
    """FIXED: Akurat detect 35+ bahasa dengan weighted scoring - Spanish/ID/Swedish/Polish/Czech/Greek/Hebrew."""
    if not text:
        return ("EN", "English")
    
    t = text.lower().strip()
    
    lang_keywords = {
        "ID": ["verifikasi", "kode", "perangkat", "rahasia", "masukkan", "anda", "akun", "kata sandi", "konfirmasi", "autentikasi", "keamanan", "sandi", "masuk", "lupa sandi"],
        "EN": ["verification", "code", "verify", "confirm", "device", "secret", "enter", "your", "account", "password", "pin", "otp", "authenticate", "security", "login", "access"],
        "ES": ["verificación", "código", "dispositivo", "secreto", "ingresa", "ingrese", "tu", "su", "cuenta", "contraseña", "clave", "confirma", "confirme", "autenticación", "seguridad", "acceso", "ingreso", "verificar"],
        "PT": ["verificação", "código", "dispositivo", "segredo", "insira", "sua", "seu", "conta", "senha", "confirme", "autenticação", "segurança", "acesso", "ingresse"],
        "FR": ["vérification", "code", "vérifier", "appareil", "secret", "entrez", "votre", "compte", "mot de passe", "confirmez", "authentification", "sécurité", "accès"],
        "DE": ["verifizierung", "code", "gerät", "geheimnis", "geben sie", "ihr", "konto", "passwort", "bestätigen", "authentifizierung", "sicherheit", "zugriff"],
        "AR": ["رمز", "كود", "التحقق", "سر", "حساب", "تأكيد", "الدخول", "كلمة", "مرور", "أدخل", "تحقق", "جهاز", "تصديق"],
        "RU": ["верификация", "код", "устройство", "секрет", "введите", "ваш", "аккаунт", "пароль", "подтвердите", "аутентификация", "безопасность", "доступ"],
        "ZH": ["验证", "代码", "设备", "秘密", "输入", "您的", "账户", "密码", "确认", "安全", "访问"],
        "JA": ["認証", "コード", "デバイス", "秘密", "入力", "あなたの", "アカウント", "パスワード", "確認", "セキュリティ"],
        "KO": ["인증", "코드", "기기", "비밀", "입력", "귀하의", "계정", "비밀번호", "확인", "보안"],
        "HI": ["सत्यापन", "कोड", "डिवाइस", "गुप्त", "दर्ज करें", "आपका", "खाता", "पासवर्ड", "पुष्टि", "सुरक्षा"],
        "BN": ["যাচাইকরণ", "কোড", "ডিভাইস", "গোপন", "লিখুন", "আপনার", "অ্যাকাউন্ট", "পাসওয়ার্ড", "নিশ্চিত"],
        "UR": ["تصدیق", "کوڈ", "ڈیوائس", "خفیہ", "درج کریں", "آپ کا", "اکاؤنٹ", "پاس ورڈ"],
        "FA": ["تایید", "کد", "دستگاه", "راز", "وارد کنید", "شما", "حساب", "رمز عبور"],
        "TR": ["doğrulama", "kod", "cihaz", "gizli", "girin", "sizin", "hesap", "şifre", "onayla", "güvenlik"],
        "TH": ["การยืนยัน", "รหัส", "อุปกรณ์", "ความลับ", "ป้อน", "ของคุณ", "บัญชี", "รหัสผ่าน"],
        "VI": ["xác minh", "mã", "thiết bị", "bí mật", "nhập", "của bạn", "tài khoản", "mật khẩu"],
        "MS": ["pengesahan", "kod", "peranti", "rahsia", "masukkan", "anda", "akaun", "kata laluan"],
        "IT": ["verifica", "codice", "dispositivo", "segreto", "inserisci", "tuo", "conto", "password", "conferma", "autenticazione"],
        "NL": ["verificatie", "code", "apparaat", "geheim", "voer in", "uw", "rekening", "wachtwoord"],
        "PL": ["weryfikacja", "kod", "urządzenie", "sekret", "wprowadź", "twój", "konto", "hasło"],
        "UK": ["верифікація", "код", "пристрій", "секрет", "введіть", "ваш", "акаунт", "пароль"],
        "SV": ["verifiering", "kod", "enhet", "hemlighet", "ange", "ditt", "konto", "lösenord", "bekräfta"],
        "NO": ["verifisering", "kode", "enhet", "hemmelighet", "skriv inn", "ditt", "konto", "passord"],
        "DA": ["verifikation", "kode", "enhed", "hemmelighed", "indtast", "dit", "konto", "adgangskode"],
        "FI": ["vahvistus", "koodi", "laite", "salaisuus", "syötä", "tilisi", "salasana", "vahvista"],
        "CS": ["ověření", "kód", "zařízení", "tajemství", "zadejte", "váš", "účet", "heslo"],
        "SK": ["overenie", "kód", "zariadenie", "tajomstvo", "zadajte", "váš", "účet", "heslo"],
        "HU": ["ellenőrzés", "kód", "eszköz", "titok", "adja meg", "az ön", "fiók", "jelszó"],
        "RO": ["verificare", "cod", "dispozitiv", "secret", "introduceți", "dvs", "cont", "parolă"],
        "GR": ["επαλήθευση", "κωδικός", "συσκευή", "μυστικό", "εισάγετε", "τον", "λογαριασμό", "κωδικό πρόσβασης"],
        "EL": ["επαλήθευση", "κωδικός", "συσκευή", "μυστικό", "εισάγετε", "λογαριασμό", "κωδικό"],
        "HE": ["אימות", "קוד", "התקן", "סוד", "הזן", "את", "חשבון", "סיסמה"],
        "TL": ["pagpapatunay", "code", "device", "lihim", "ipasok", "iyong", "account", "password"],
    }
    
    # STEP 1: Check Unicode patterns FIRST (most reliable)
    if re.search(r"[\u0600-\u06FF]", text):
        if iso in ("PK", "AF"): return ("UR", "Urdu")
        if iso == "IR": return ("FA", "Persian")
        return ("AR", "Arabic")
    
    if re.search(r"[\u0980-\u09FF]", text): return ("BN", "Bengali")
    if re.search(r"[\u0900-\u097F]", text): return ("HI", "Hindi")
    if re.search(r"[\u0E00-\u0E7F]", text): return ("TH", "Thai")
    if re.search(r"[\uAC00-\uD7AF]", text): return ("KO", "Korean")
    if re.search(r"[\u3040-\u30FF]", text): return ("JA", "Japanese")
    if re.search(r"[\u0400-\u04FF]", text):
        if iso == "UA": return ("UK", "Ukrainian")
        if any(kw in t for kw in ["и", "не", "что", "вы"]): return ("RU", "Russian")
        return ("RU", "Russian")
    if re.search(r"[\u4e00-\u9fff]", text):
        if any(kw in t for kw in ["的", "了", "是", "我"]): return ("ZH", "Chinese")
        return ("ZH", "Chinese")
    if re.search(r"[\u05D0-\u05FF]", text): return ("HE", "Hebrew")
    
    # STEP 2: Keyword-based scoring
    scores = {}
    for lang, keywords in lang_keywords.items():
        score = sum(1 for kw in keywords if kw in t)
        if score > 0:
            scores[lang] = score
    
    if scores:
        best = max(scores, key=scores.get)
        lang_names = {
            "ID": ("ID", "Indonesian"), "EN": ("EN", "English"), "ES": ("ES", "Spanish"),
            "PT": ("PT", "Portuguese"), "FR": ("FR", "French"), "AR": ("AR", "Arabic"),
            "DE": ("DE", "German"), "RU": ("RU", "Russian"), "ZH": ("ZH", "Chinese"),
            "JA": ("JA", "Japanese"), "KO": ("KO", "Korean"), "HI": ("HI", "Hindi"),
            "BN": ("BN", "Bengali"), "UR": ("UR", "Urdu"), "FA": ("FA", "Persian"),
            "TR": ("TR", "Turkish"), "TH": ("TH", "Thai"), "VI": ("VI", "Vietnamese"),
            "MS": ("MS", "Malay"), "IT": ("IT", "Italian"), "NL": ("NL", "Dutch"),
            "PL": ("PL", "Polish"), "UK": ("UK", "Ukrainian"), "SV": ("SV", "Swedish"),
            "NO": ("NO", "Norwegian"), "DA": ("DA", "Danish"), "FI": ("FI", "Finnish"),
            "CS": ("CS", "Czech"), "SK": ("SK", "Slovak"), "HU": ("HU", "Hungarian"),
            "RO": ("RO", "Romanian"), "GR": ("GR", "Greek"), "EL": ("EL", "Greek"),
            "HE": ("HE", "Hebrew"), "TL": ("TL", "Tagalog"),
        }
        return lang_names.get(best, ("EN", "English"))
    
    return ("EN", "English")


def _render_message_from_template(tmpl: dict, panel_name: str, number: str, otp: str, svc_id: str,
                                   message: str, cc: str = "", extra: dict = None):
    country = countries.get(cc, {"flag": "🌍", "name": cc or "Unknown", "iso": ""})
    svc     = services.get(svc_id, {"icon": "📱", "name": (svc_id or "Unknown").capitalize()})
    num_clean = re.sub(r"\D", "", str(number))
    svc_name  = str(svc.get("name", "Unknown"))
    iso       = str(country.get("iso", ""))
    flag_plain = country.get("flag", "🌍")
    lang_short, lang_full = detect_full_language(message, iso)

    _tpl_emojis = emoji_settings.get("template", {}) or {}
    def _tpl_char_html(key, default):
        entry = _tpl_emojis.get(key) or {"char": default, "id": None}
        return emoji_html(entry)

    vars_ = {
        "{flag}":           get_country_flag_html(cc) if cc else html.escape(flag_plain),
        "{flang}":          get_country_flag_html(cc) if cc else html.escape(flag_plain),
        "{flag_plain}":     html.escape(flag_plain),
        "{country}":        html.escape(str(country.get("name", cc or "Unknown"))),
        "{iso}":            html.escape(iso.upper()),
        "{country_iso}":    html.escape(iso),
        "{country_tag}":    html.escape(f"{flag_plain} {iso} {country.get('name', cc or 'Unknown')}".strip()),
        "{number}":         html.escape(num_clean),
        "{number_masked}":  _mask_number_html(num_clean),
        "{prefix}":         _prefix_number_html(num_clean),
        "{Prefix}":         _prefix_number_html(num_clean),
        ":prefix":          _prefix_number_html(num_clean),
        ":Prefix":          _prefix_number_html(num_clean),
        "{otp}":            html.escape(str(otp)),
        "{service}":        html.escape(svc_name),
        "{sender}":         html.escape(svc_name),
        "{svc_icon}":       get_svc_icon_html(svc_id),
        "{svc_short}":      html.escape(_svc_short(svc_name)),
        "{panel}":          html.escape(str(panel_name)),
        "{message}":        html.escape((message or "")[:120]),
        "{time}":           html.escape(now_wib().strftime("%H:%M")),
        "{language}":       html.escape(lang_short),
        "{lang_short}":     html.escape(lang_short),
        "{lang_full}":      html.escape(lang_full),
        "{e1}":             _tpl_char_html("e1", "✅"),
        "{e2}":             _tpl_char_html("e2", "📌"),
        "{e3}":             _tpl_char_html("e3", "📎"),
        "{e4}":             _tpl_char_html("e4", "🔥"),
        "{e5}":             _tpl_char_html("e5", "⚡"),
    }
    if extra:
        vars_.update({f"{{{k}}}": html.escape(str(v)) for k, v in extra.items()})

    def subst(s):
        for k, v in vars_.items():
            s = s.replace(k, str(v))
        return s

    text = subst(_md_to_html(tmpl.get("text", DEFAULT_OTP_TEMPLATE["text"])))
    btns = tmpl.get("buttons", DEFAULT_OTP_TEMPLATE["buttons"])

    svc_icon_id = get_svc_icon_id(svc_id)

    _VALID_BTN_STYLES = ("primary", "success", "danger")

    def _btn_style(b: dict = None):
        b = b or {}
        style = b.get("style", "success")
        if style not in _VALID_BTN_STYLES:
            style = "success"
        kw = {"style": style}
        btn_icon_id = b.get("icon_id")
        if btn_icon_id:
            kw["icon_custom_emoji_id"] = btn_icon_id
        else:
            want_icon = b.get("icon", False)
            if want_icon and svc_icon_id:
                kw["icon_custom_emoji_id"] = svc_icon_id
        return kw

    kb_rows, cur_row = [], []
    for b in btns:
        if b.get("type") == "sep":
            if cur_row:
                kb_rows.append(cur_row)
                cur_row = []
            continue
        label = subst(b.get("label", "Button"))
        btype = b.get("type", "copy")
        if btype == "link":
            btn = InlineKeyboardButton(label, url=subst(b.get("value", "")), api_kwargs=_btn_style(b))
        elif btype == "copy":
            btn = InlineKeyboardButton(label, copy_text=CopyTextButton(text=subst(b.get("value", str(otp)))), api_kwargs=_btn_style(b))
        else:
            btn = InlineKeyboardButton(label, copy_text=CopyTextButton(text=str(otp)), api_kwargs=_btn_style(b))
        cur_row.append(btn)
    if cur_row:
        kb_rows.append(cur_row)

    kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    return text, kb

def render_otp_message(panel_name: str, number: str, otp: str, svc_id: str, message: str, cc: str = ""):
    """Render pesan OTP untuk GRUP, pakai template grup (Settings → Template)."""
    tmpl = get_otp_template()
    return _render_message_from_template(tmpl, panel_name, number, otp, svc_id, message, cc)

def render_user_otp_message(panel_name: str, number: str, otp: str, svc_id: str, message: str,
                             cc: str = "", earned: float = 0.0, balance: float = 0.0):
    """Render pesan OTP untuk USER (chat pribadi), pakai template user (Settings → Template User)."""
    tmpl = get_otp_user_template()
    extra = {"earned": f"{earned:.2f}", "balance": f"{balance:.2f}"}
    return _render_message_from_template(tmpl, panel_name, number, otp, svc_id, message, cc, extra=extra)

def scraper_extract_otp(message: str):
    if not message: return None
    cleaned = re.sub(r'\b(19|20)\d{2}[-/]\d{2}[-/]\d{2}\b', '', message)
    cleaned = re.sub(r'\b(19|20)\d{2}\b', '', cleaned)
    for p in [
        r'FB-(\d{5})', r'[Gg]-(\d{6})',
        r'(?:otp|code|pin|verification|كود|رمز|কোড)[^\d]{0,15}(\d{4,8})',
        r'(?:is|has|:)\s*(\d{4,8})\b',
        r'(\d{3}[- ]\d{3})', r'\b(\d{6})\b', r'\b(\d{4,8})\b',
    ]:
        m = re.search(p, cleaned, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(' ', '').replace('-', '')
            if 4 <= len(raw) <= 8:
                return raw
    return None

def scraper_detect_service(message: str, range_name: str = "") -> str:
    combined = (message + " " + range_name).lower()
    for svc, pat in {
        'whatsapp': r'whatsapp|واتساب', 'telegram': r'telegram',
        'facebook': r'facebook|fb\.com', 'instagram': r'instagram',
        'google':   r'google|gmail',     'microsoft': r'microsoft|outlook',
        'twitter':  r'twitter|x\.com',   'tiktok':    r'tiktok',
        'snapchat': r'snapchat',
    }.items():
        if re.search(pat, combined, re.IGNORECASE):
            return svc
    return "other"

def _panel_get_fns(name: str, url: str, ptype: str, fp=None):
    """Router: pilih login/fetch function yang tepat dari panel_fetchers.py sesuai ptype."""
    from panel_fetchers import (
        ints_login, ints_fetch,
        ims_login, ims_fetch,
        konekta_login, konekta_fetch,
        panel_login as _std_login, panel_fetch as _std_fetch,
        purple_sms_login, purple_sms_fetch,
        new_panel_login, new_panel_fetch,
        timesms_login, timesms_fetch,
        sms_login, sms_fetch,
        falcon_login, falcon_fetch,
        porsha_login, porsha_fetch,
        nexa_login, nexa_fetch,
        aleius_login, aleius_fetch,
        mj_sms_login, mj_sms_fetch,
        mj_sms_api_login, mj_sms_api_fetch,
        thirdwave_login, thirdwave_fetch,
        elite_login, elite_fetch,
        elite_sms_api_login, elite_sms_api_fetch,
        elite_sms_v1_login, elite_sms_v1_fetch,
        rez_sms_login, rez_sms_fetch,
        axon_login, axon_fetch,
        smsnode_login, smsnode_fetch,
        augestel_login, augestel_fetch,
        ksi_login, ksi_fetch,
        gren_sms_login, gren_sms_fetch,
        xisora_login, xisora_fetch,
        mbcs_login, mbcs_fetch,
        mbcs_api_login, mbcs_api_fetch,
        proofsms_fetch,
        xms_login, xms_fetch,
        zonesms_login, zonesms_fetch,
        zedsms_login, zedsms_fetch,
    )
    bn = _BN_FOR_TYPE.get(ptype, name)

    if ptype == "timesms":
        return bn, (lambda u, p: timesms_login(bn, u, p, url)), (lambda s: timesms_fetch(bn, s, url))
    if ptype == "sms":
        return bn, (lambda u, p: sms_login(bn, u, p, url)), (lambda s: sms_fetch(s, url))
    if ptype == "falcon":
        return bn, (lambda u, p: falcon_login(bn, u, p, url)), (lambda s: falcon_fetch(s, url))
    if ptype == "porsha":
        return bn, (lambda u, p: porsha_login(bn, u, p, url)), (lambda s: porsha_fetch(bn, s, url))
    if ptype == "nexa":
        return bn, (lambda u, p: nexa_login(bn, u, p, url)), (lambda s: nexa_fetch(bn, s, url))
    if ptype == "aleius":
        return bn, (lambda u, p: aleius_login(bn, u, p, url)), (lambda s: aleius_fetch(bn, s, url))
    if ptype == "mjsms":
        return bn, (lambda u, p: mj_sms_login(bn, u, p, url)), (lambda s: mj_sms_fetch(bn, s, url))
    if ptype == "mjsms_api":
        return bn, (lambda u, p: mj_sms_api_login(bn, u, p, url)), (lambda s: mj_sms_api_fetch(s, url))
    if ptype == "ims":
        return bn, (lambda u, p: ims_login(u, p, url)), (lambda s: ims_fetch(s, url))
    if ptype == "konekta":
        return bn, (lambda u, p: konekta_login(u, p)), (lambda s: konekta_fetch(s))
    if ptype in ("roxy", "voicegate", "numberpanel", "sniper"):
        return bn, (lambda u, p: new_panel_login(bn, u, p, url)), (lambda s: new_panel_fetch(bn, s, url))
    if ptype == "purplesms":
        return bn, (lambda u, p: purple_sms_login(bn, u, p, url)), (lambda s: purple_sms_fetch(s, url))
    if ptype == "standard":
        return bn, (lambda u, p: _std_login(bn, u, p, url)), (lambda s: _std_fetch(s, url))
    if ptype == "proofsms":
        return bn, (lambda u, p: ints_login(bn, u, p, url, fp)), (lambda s: proofsms_fetch(s, url))
    if ptype == "xms":
        return bn, (lambda u, p: xms_login(bn, u, p, url)), (lambda s: xms_fetch(bn, s, url))
    if ptype == "zonesms":
        return bn, (lambda u, p: zonesms_login(bn, u, p, url)), (lambda s: zonesms_fetch(bn, s, url))
    if ptype == "zedsms":
        return bn, (lambda u, p: zedsms_login(bn, u, p, url)), (lambda s: zedsms_fetch(bn, s, url))
    if ptype == "thirdwave":
        return bn, (lambda u, p: thirdwave_login(bn, u, p, url)), (lambda s: thirdwave_fetch(s, url))
    if ptype == "elite_sms":
        return bn, (lambda u, p: elite_login(bn, u, p, url)), (lambda s: elite_fetch(s, url))
    if ptype == "elite_sms_api":
        return bn, (lambda u, p: elite_sms_api_login(bn, u, p, url)), (lambda s: elite_sms_api_fetch(s, url))
    if ptype == "elite_sms_v1":
        return bn, (lambda u, p: elite_sms_v1_login(bn, u, p, url)), (lambda s: elite_sms_v1_fetch(s, url))
    if ptype == "rez_sms":
        return bn, (lambda u, p: rez_sms_login(bn, u, p, url)), (lambda s: rez_sms_fetch(s, url))
    if ptype == "axon":
        return bn, (lambda u, p: axon_login(bn, u, p, url)), (lambda s: axon_fetch(s, url))
    if ptype == "smsnode":
        return bn, (lambda u, p: smsnode_login(bn, u, p, url)), (lambda s: smsnode_fetch(s, url))
    if ptype == "augestel":
        return bn, (lambda u, p: augestel_login(bn, u, p, url)), (lambda s: augestel_fetch(s, url))
    if ptype == "ksi":
        return bn, (lambda u, p: ksi_login(bn, u, p, url)), (lambda s: ksi_fetch(s, url))
    if ptype == "gren_sms":
        return bn, (lambda u, p: gren_sms_login(bn, u, p, url)), (lambda s: gren_sms_fetch(bn, s, url))
    if ptype == "xisora":
        return bn, (lambda u, p: xisora_login(bn, u, p, url)), (lambda s: xisora_fetch(s, url))
    if ptype == "mbcs":
        return bn, (lambda u, p: mbcs_login(bn, u, p, url)), (lambda s: mbcs_fetch(bn, s, url))
    if ptype == "mbcs_api":
        return bn, (lambda u, p: mbcs_api_login(bn, u, p, url)), (lambda s: mbcs_api_fetch(s, url))
    # default → ints (HADI/Seven1Tel/Wolf/Gaza/MAIT dsb pakai engine yang sama)
    return bn, (lambda u, p: ints_login(bn, u, p, url, fp)), (lambda s: ints_fetch(bn, s, url))

def _panel_delay(ptype: str) -> int:
    return {"timesms": 15, "sniper": 6, "roxy": 6, "voicegate": 6,
            "numberpanel": 6, "xms": 8, "sms": 4, "falcon": 4, "porsha": 5,
            "nexa": 5, "thirdwave": 5, "elite_sms": 5, "elite_sms_api": 15,
            "elite_sms_v1": 10, "rez_sms": 10,
             "axon": 5, "smsnode": 5, "mjsms": 5, "mjsms_api": 5,
             "augestel": 60, "ksi": 60, "gren_sms": 8, "xisora": 5,
             "mbcs": 10, "mbcs_api": 15}.get(ptype, 3)

POLL_INTERVAL_MIN_SECONDS = 1
POLL_INTERVAL_MAX_SECONDS = 300
PANEL_MIN_POLL_INTERVAL_SECONDS = {"augestel": 13, "ksi": 13}

def _panel_min_poll_interval(ptype: str) -> int:
    return PANEL_MIN_POLL_INTERVAL_SECONDS.get(
        str(ptype or "").strip().lower(),
        POLL_INTERVAL_MIN_SECONDS,
    )

def _account_poll_interval(ptype: str, account_row) -> int:
    """Return the per-account interval, falling back for legacy accounts."""
    minimum = _panel_min_poll_interval(ptype)
    try:
        value = int(account_row["poll_interval"])
    except (KeyError, TypeError, ValueError):
        value = 0
    if value < minimum:
        value = _panel_delay(ptype)
    return max(minimum, min(POLL_INTERVAL_MAX_SECONDS, value))

def _parse_poll_interval(raw: str, ptype: str = ""):
    """Parse an admin-provided interval in seconds; return None when invalid."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not _panel_min_poll_interval(ptype) <= value <= POLL_INTERVAL_MAX_SECONDS:
        return None
    return value

def _is_webhook_panel(ptype: str) -> bool:
    return str(ptype or "").strip().lower() in {"augestel", "ksi", "elite_sms_api"}


def _webhook_requires_secret(ptype: str) -> bool:
    """Only providers with documented HMAC secrets require this wizard step."""
    return str(ptype or "").strip().lower() in {"augestel", "ksi"}

def _optional_poll_interval(raw: str, ptype: str):
    """Allow skip for the API/webhook panels and use their safe default."""
    if str(raw or "").strip().lower() in {"skip", "-", "kosong", "none", "default"}:
        return _panel_delay(ptype)
    return _parse_poll_interval(raw, ptype)

def _clean_optional_webhook_value(raw: str) -> str:
    value = str(raw or "").strip()
    return "" if value.lower() in {"skip", "-", "kosong", "none", "reset"} else value

def _auto_delete_enabled() -> bool:
    return bool(settings.get("autoDeleteOtpEnabled", False))

def _auto_delete_seconds() -> int:
    minutes = settings.get("autoDeleteOtpMinutes", 5)
    try:
        minutes = float(minutes)
    except (TypeError, ValueError):
        minutes = 5
    return max(0, int(minutes * 60))

async def _delete_message_after(app, chat_id, message_id, delay_seconds: int):
    """Tunggu <code>delay_seconds</code> lalu hapus 1 pesan di grup. Dipanggil
    lewat asyncio.create_task supaya tidak nge-block loop pengiriman OTP."""
    try:
        await asyncio.sleep(delay_seconds)
        await app.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        # Wajar gagal kalau pesan sudah dihapus manual/duluan oleh user lain,
        # atau bot kehilangan izin hapus pesan — cukup dicatat di log saja.
        logger.info(f"ℹ️ Auto-delete OTP: gagal hapus pesan {message_id} di {chat_id}: {e}")

def schedule_auto_delete(app, sent_message):
    """Jadwalkan penghapusan otomatis 1 pesan OTP di grup, HANYA kalau fitur
    Auto-Delete OTP sedang di-ON lewat Admin → Settings. Dipanggil setiap kali
    bot berhasil kirim 1 pesan OTP ke grup."""
    if not app or not sent_message or not _auto_delete_enabled():
        return
    delay = _auto_delete_seconds()
    if delay <= 0:
        return
    try:
        chat_id    = sent_message.chat_id
        message_id = sent_message.message_id
    except AttributeError:
        return
    asyncio.create_task(_delete_message_after(app, chat_id, message_id, delay))

def schedule_auto_delete_ids(app, chat_id, message_id):
    """Sama seperti schedule_auto_delete(), tapi utk pesan OTP mentah yang
    SUDAH ada di grup (bukan yang bot ini kirim sendiri — mis. pesan dari
    akun WA/SMS yang diteruskan langsung ke Grup OTP). Dipakai supaya fitur
    Auto-Delete tetap berlaku walau OTP masuk lewat jalur grup, bukan cuma
    jalur panel scraper."""
    if not app or chat_id is None or message_id is None or not _auto_delete_enabled():
        return
    delay = _auto_delete_seconds()
    if delay <= 0:
        return
    asyncio.create_task(_delete_message_after(app, chat_id, message_id, delay))

async def _panel_send_to_groups(app, text, kb):
    """Kirim OTP ke semua grup yang dikonfigurasi di Settings → Groups."""
    for gid in get_otp_groups():
        try:
            sent = await safe_send_message(app.bot, int(gid), text, parse_mode="HTML", reply_markup=kb)
            schedule_auto_delete(app, sent)
        except Exception as e:
            logger.error(f"❌ group send fail {gid}: {e}")

def _parse_panel_ts(ts):
    """Coba parse timestamp SMS yang dikembalikan API panel jadi datetime UTC.
    Tiap jenis panel bisa punya format berbeda (ISO, 'YYYY-MM-DD HH:MM:SS',
    unix epoch detik/milidetik, dll) — dicoba satu-satu. Kalau semua gagal,
    return None; urutan dari panel akan dipakai sebagai fallback."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            v = float(ts)
            if v > 10_000_000_000:  # kemungkinan milidetik, bukan detik
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None
    s = str(ts).strip()
    if not s:
        return None
    if s.isdigit():
        try:
            v = float(s)
            if v > 10_000_000_000:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _webhook_provider_from_headers(request):
    """Detect a supported webhook dialect from provider headers or path."""
    path = str(getattr(request, "path", "") or "").rstrip("/")
    if path in {"/webhooks/elite_sms", "/webhooks/elite_sms_api"}:
        return "elite_sms_api"
    if any(request.headers.get(name) for name in (
        "X-Elite-SMS-Event",
        "X-Elite-SMS-Signature",
        "X-Webhook-Event",
    )):
        return "elite_sms_api"
    if any(request.headers.get(name) for name in (
        "X-KSIIPRNTECHNOLOGY-Event",
        "X-KSIIPRNTECHNOLOGY-Signature",
        "X-KSIIPRNTECHNOLOGY-Timestamp",
    )):
        return "ksi"
    if any(request.headers.get(name) for name in (
        "X-Augestel-Event",
        "X-Augestel-Signature",
        "X-Augestel-Timestamp",
    )):
        return "augestel"
    return ""


WEBHOOK_EVENTS = frozenset({
    "message.received",
    "number.assigned",
    "number.removed",
    "earnings.daily",
    "delivery.confirmed",
    "delivery.pending",
    "settlement.paid",
})


def _webhook_header_names(provider):
    if provider == "elite_sms_api":
        return (
            "X-Elite-SMS-Event",
            "X-Elite-SMS-Signature",
            "X-Elite-SMS-Timestamp",
        )
    prefix = "X-KSIIPRNTECHNOLOGY" if provider == "ksi" else "X-Augestel"
    return (
        f"{prefix}-Event",
        f"{prefix}-Signature",
        f"{prefix}-Timestamp",
    )


def _webhook_account_match(request, body, provider):
    """Find exactly one API-panel account whose configured secret verifies."""
    import hmac

    if provider == "elite_sms_api":
        request_path = str(getattr(request, "path", "") or "").rstrip("/")
        candidates = []
        for panel in get_panels():
            if panel["ptype"] != provider:
                continue
            for account in get_all_accounts(panel["name"]):
                raw_url = str(account["webhook_url"] or "").strip()
                if not raw_url:
                    continue
                parsed = urllib.parse.urlparse(
                    raw_url if "://" in raw_url else f"http://local{raw_url}"
                )
                configured_path = parsed.path.rstrip("/") or "/"
                if configured_path == request_path:
                    candidates.append((panel, account))

        # Elite SMS does not expose a signing-secret field in its webhook UI.
        # Prefer its API key when the provider sends one; otherwise an exact,
        # unique configured callback path is the account binding.
        auth_value = str(
            request.headers.get("X-API-Key")
            or request.headers.get("X-Elite-SMS-Key")
            or request.headers.get("Authorization", "")
        ).strip()
        if auth_value.lower().startswith("bearer "):
            auth_value = auth_value[7:].strip()
        if auth_value:
            candidates = [
                (panel, account)
                for panel, account in candidates
                if hmac.compare_digest(auth_value, str(account["password"] or ""))
            ]
        return candidates[0] if len(candidates) == 1 else None

    event_header, signature_header, timestamp_header = _webhook_header_names(provider)
    signature = str(request.headers.get(signature_header, "")).strip()
    if not signature.lower().startswith("sha256="):
        return None
    supplied = signature.split("=", 1)[1].strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
        return None
    matches = []
    for panel in get_panels():
        if panel["ptype"] != provider:
            continue
        for account in get_all_accounts(panel["name"]):
            secret = str(account["webhook_secret"] or "").strip()
            if secret and hmac.compare_digest(
                supplied.lower(),
                hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest().lower(),
            ):
                matches.append((panel, account))
    return matches[0] if len(matches) == 1 else None


def _webhook_event_name(payload):
    if not isinstance(payload, dict):
        return ""
    event = str(
        payload.get("event")
        or payload.get("type")
        or payload.get("event_type")
        or ""
    ).strip().lower()
    return event if event in WEBHOOK_EVENTS else ""


def _webhook_payload_row(payload, provider=""):
    """Convert supported message/delivery webhook envelopes to panel rows."""
    if not isinstance(payload, dict):
        return None
    event_name = _webhook_event_name(payload)
    if event_name == "message.received":
        pass
    elif provider == "elite_sms_api" and event_name in {
        "delivery.confirmed", "delivery.pending",
    }:
        pass
    else:
        return None
    data = payload.get("data")
    if not isinstance(data, dict) and provider == "elite_sms_api":
        # Accept both {event, data:{...}} and flat Elite SMS event bodies.
        data = payload
    if not isinstance(data, dict):
        return None
    source = str(
        data.get("source")
        or data.get("sender")
        or data.get("service")
        or data.get("cli")
        or data.get("panel")
        or ""
    ).strip()
    number = str(
        data.get("number")
        or data.get("phone_number")
        or data.get("recipient")
        or data.get("destination")
        or ""
    ).strip()
    message = str(
        data.get("message")
        or data.get("message_body")
        or data.get("text")
        or data.get("body")
        or data.get("otp")
        or ""
    ).strip()
    if not source or not number or not message:
        return None
    event_id = str(data.get("id") or payload.get("id") or "").strip()
    if not event_id:
        event_id = hashlib.sha256(
            json.dumps(
                {"source": source, "number": number, "message": message,
                 "received_at": str(
                     data.get("received_at")
                     or data.get("time")
                     or payload.get("timestamp")
                     or ""
                 )},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    return (
        str(
            data.get("received_at")
            or data.get("time")
            or payload.get("timestamp")
            or ""
        ),
        event_id,
        number,
        source,
        None,
        message,
    )


def _webhook_url_error(raw):
    """Validate the provider's public HTTPS endpoint requirement."""
    value = str(raw or "").strip()
    if not value or value.lower() in {"skip", "-", "kosong", "none"}:
        return ""
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return "URL webhook tidak valid."
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return "URL webhook harus berupa alamat publik https://."
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return "URL webhook tidak boleh menunjuk ke host internal."
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ):
        return "URL webhook tidak boleh menunjuk ke alamat internal atau loopback."
    return ""


def _webhook_paths_for_ptype(ptype):
    default_slug = {
        "elite_sms_api": "elite_sms",
    }.get(ptype, ptype)
    paths = {f"/webhooks/{default_slug}"}
    for panel in get_panels():
        if panel["ptype"] != ptype:
            continue
        for account in get_all_accounts(panel["name"]):
            raw = str(account["webhook_url"] or "").strip()
            if not raw:
                continue
            parsed = urllib.parse.urlparse(raw if "://" in raw else f"http://local{raw}")
            path = parsed.path.rstrip("/")
            if path and path not in {"/otp", "/health"}:
                paths.add(path if path.startswith("/") else f"/{path}")
    return paths


async def _forward_webhook_panel_row(app, panel, account, row):
    """Forward one verified webhook event through the normal OTP pipeline."""
    ts, event_id, number, source, _blank, sms = row
    otp = scraper_extract_otp(sms)
    if not otp:
        return "ignored"
    bn = panel["name"]
    async with panel_webhook_lock:
        if _panel_otp_in_history(number, otp) or _is_duplicate_otp(number, otp):
            return "duplicate"
        num_clean = re.sub(r"\D", "", str(number)).lstrip("0")
        matched = find_active_number(num_clean)
        cc = active_numbers[matched].get("countryCode", "") if matched else guess_cc_from_number(num_clean)
        if matched and not _number_still_assigned(active_numbers[matched]["userId"], matched):
            active_numbers.pop(matched, None)
            rebuild_suffix_index()
            await async_save_active()
            matched = None
            cc = guess_cc_from_number(num_clean)
        svc_id = scraper_detect_service(sms, source)
        text, kb = render_otp_message(bn, num_clean, otp, svc_id, sms, cc)
        user_id = active_numbers[matched]["userId"] if matched else None
        asyncio.create_task(record_otp_event(f"panel_{bn}", user_id, cc, svc_id, num_clean, otp))
        await _panel_send_to_groups(app, text, kb)

        earned = 0.0
        if matched:
            uid = active_numbers[matched]["userId"]
            earned = await add_earning(uid, cc)
            balance = get_user_earnings(uid)["balance"]
            user_text, user_kb = render_user_otp_message(
                bn, matched, otp, svc_id, sms, cc, earned=earned, balance=balance
            )
            try:
                sent = await safe_send_message(
                    app.bot, int(uid), user_text, parse_mode="HTML", reply_markup=user_kb
                )
                await _track_otp_notify_msg(matched, sent.message_id)
            except Exception as exc:
                logger.error(f"❌ webhook notify error uid={uid}: {exc}")

        otp_log.append({
            "phoneNumber": num_clean,
            "userId": user_id,
            "countryCode": cc,
            "service": svc_id,
            "otpCode": otp,
            "earned": earned,
            "messageId": None,
            "delivered": True,
            "source": f"panel_{bn}",
            "timestamp": now_wib().isoformat(),
        })
        await async_save_otp_log()
        return "sent"


async def _process_verified_webhook(app, panel, account, payload, event_name):
    """Process after the HTTP 200 ACK has been sent to the provider."""
    if event_name != "message.received":
        logger.info(
            "✅ webhook %s acknowledged for panel=%s account=%s",
            event_name,
            panel["name"],
            account["username"],
        )
        return "acknowledged"
    row = _webhook_payload_row(payload, panel["ptype"])
    if row is None:
        logger.warning(
            "⚠️ webhook message.received missing source/number/message "
            "for panel=%s account=%s",
            panel["name"],
            account["username"],
        )
        return "ignored"
    return await _forward_webhook_panel_row(app, panel, account, row)


def _webhook_task_done(task):
    try:
        status = task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("❌ background webhook processing failed")
    else:
        logger.info("📨 background webhook processing finished: %s", status)


async def panel_webhook_handler(request, expected_ptype=None):
    """Verify signed webhooks and ACK before doing slow downstream work."""
    try:
        if request.content_length and request.content_length > 1024 * 1024:
            return aio_web.json_response({"ok": False, "error": "body too large"}, status=413)
        body = await request.read()
        if len(body) > 1024 * 1024:
            return aio_web.json_response({"ok": False, "error": "body too large"}, status=413)
        provider = expected_ptype or _webhook_provider_from_headers(request)
        if provider not in {"augestel", "ksi", "elite_sms_api"}:
            return aio_web.json_response({"ok": False, "error": "unknown provider"}, status=400)
        event_header, _signature_header, timestamp_header = _webhook_header_names(provider)
        timestamp = str(request.headers.get(timestamp_header, "")).strip()
        if not timestamp and provider != "elite_sms_api":
            return aio_web.json_response({"ok": False, "error": "timestamp required"}, status=400)
        if timestamp:
            try:
                parsed_ts = datetime.fromisoformat(
                    timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
                )
            except (TypeError, ValueError, OverflowError):
                return aio_web.json_response({"ok": False, "error": "invalid timestamp"}, status=400)
            if parsed_ts.tzinfo is None or abs((datetime.now(timezone.utc) - parsed_ts.astimezone(timezone.utc)).total_seconds()) > 900:
                return aio_web.json_response({"ok": False, "error": "invalid or expired timestamp"}, status=400)
        # Verify the HMAC against the exact bytes before parsing/re-encoding JSON.
        match = _webhook_account_match(request, body, provider)
        if not match:
            return aio_web.json_response({"ok": False, "error": "invalid webhook signature"}, status=401)
        payload = json.loads(body.decode("utf-8"))
        event_name = _webhook_event_name(payload)
        if not event_name:
            return aio_web.json_response({"ok": False, "error": "unsupported event"}, status=400)
        payload_event = _webhook_event_name(payload)
        header_event = str(request.headers.get(event_header, "")).strip().lower()
        if header_event and payload_event != header_event:
            return aio_web.json_response({"ok": False, "error": "event header mismatch"}, status=400)
        if not isinstance(payload.get("data"), dict):
            if provider != "elite_sms_api":
                return aio_web.json_response({"ok": False, "error": "invalid event envelope"}, status=400)
        if provider != "elite_sms_api" and not payload.get("timestamp"):
            return aio_web.json_response({"ok": False, "error": "invalid event envelope"}, status=400)
        task = asyncio.create_task(
            _process_verified_webhook(
                request.app["telegram_app"],
                match[0],
                match[1],
                payload,
                event_name,
            )
        )
        task.add_done_callback(_webhook_task_done)
        return aio_web.json_response(
            {"ok": True, "accepted": True, "queued": True, "event": event_name},
            status=200,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return aio_web.json_response({"ok": False, "error": "invalid JSON or timestamp"}, status=400)
    except Exception as exc:
        logger.error(f"❌ panel webhook error: {exc}")
        return aio_web.json_response({"ok": False, "error": "internal webhook error"}, status=500)


async def run_account(panel_row, account_row, app):
    """1 loop per account (persis model SC_jadi: 1 panel bisa punya banyak akun,
    tiap akun jalan independen). OTP hasil fetch tetap dikirim ke grup DAN
    ke user pemilik nomor (DM bot) sesuai active_numbers — sama seperti sebelumnya."""
    aid      = account_row["id"]
    bn       = panel_row["name"]
    url      = (panel_row["url"] or "").rstrip("/")
    ptype    = panel_row["ptype"]
    fp       = panel_row["fp"]
    username = account_row["username"]
    password = account_row["password"]
    poll_interval = _account_poll_interval(ptype, account_row)

    bn, login_fn, fetch_fn = _panel_get_fns(bn, url, ptype, fp)
    logger.info(
        f"🚀 [{bn}] account `{username}` (id={aid}) started "
        f"— polling every {poll_interval}s"
    )
    otp_panel_status[aid] = "running"

    session_info      = None
    fail_count        = 0
    previous_otps     = set()

    while True:
        try:
            # ── Login jika belum ada session ──
            if session_info is None:
                try:
                    session_info = await asyncio.to_thread(login_fn, username, password)
                    otp_panel_session[aid] = session_info
                    if otp_panel_status.get(aid) == "error":
                        asyncio.create_task(alert_owner_panel_recovered(app, bn, username))
                    fail_count = 0
                    otp_panel_status[aid] = "running"
                    logger.info(f"✅ [{bn}] {username} login OK")
                except Exception as e:
                    fail_count += 1
                    logger.error(f"❌ [{bn}] {username} login gagal ({fail_count}/5): {e}")
                    if fail_count >= 5:
                        otp_panel_status[aid] = "error"
                        logger.error(f"🛑 [{bn}] {username} login gagal 5x, coba lagi 5 menit lagi.")
                        alert_type = _classify_panel_error(str(e))
                        if alert_type == "api":
                            alert_type = "login"  # gagal login berulang → anggap login expired/invalid
                        asyncio.create_task(alert_owner_panel(app, bn, username, alert_type, str(e)))
                        await asyncio.sleep(300)
                        fail_count = 0
                    else:
                        await asyncio.sleep(30)
                    continue

            # ── Fetch SMS/OTP dari panel ──
            try:
                rows = await asyncio.to_thread(fetch_fn, session_info)
            except Exception as e:
                logger.error(f"❌ [{bn}] {username} fetch error: {e}")
                rows = None
                alert_type = _classify_panel_error(str(e))
                asyncio.create_task(alert_owner_panel(app, bn, username, alert_type, str(e)))

            if rows is None:
                # Session expired → paksa re-login
                logger.info(f"🔄 [{bn}] {username} session expired, re-login...")
                session_info = None
                await asyncio.sleep(3)
                continue

            rows = _latest_panel_rows(rows)
            logger.info(
                f"📥 [{bn}] {username} panel rows: "
                f"{len(rows)} terbaru (maksimal {PANEL_LATEST_ROWS_LIMIT})"
            )

            for row in rows:
                try:
                    ts, rid, number, rng, _blank, sms = row
                except Exception:
                    continue

                otp = scraper_extract_otp(sms)
                # Aleius can deliberately hide the OTP or return a row with
                # only the number. Keep forwarding those rows to the group;
                # user-DM/earning remains OTP-only.
                group_only_hidden_otp = ptype == "aleius" and bool(
                    re.sub(r"\D", "", str(number))
                )
                if not otp and not group_only_hidden_otp:
                    continue
                display_otp = otp or "Hidden"

                otp_id = f"{bn}_{aid}_{number}_{display_otp}_{ts}"
                if otp_id in previous_otps:
                    continue
                previous_otps.add(otp_id)
                if len(previous_otps) > 50000:
                    previous_otps = set(list(previous_otps)[-20000:])

                # Riwayat OTP persisten adalah sumber deduplikasi utama.
                # Jangan membuang OTP hanya karena timestamp-nya lama:
                # setelah restart, 30 row terbaru tetap harus diproses jika
                # belum pernah ada di riwayat.
                if otp and _panel_otp_in_history(number, otp):
                    logger.info(
                        f"⏭️ [{bn}] OTP +{number}/{otp} sudah ada di riwayat, "
                        "tidak diteruskan ulang."
                    )
                    continue

                svc_id = scraper_detect_service(sms, rng)

                # ── Reload active_numbers list biar fresh ──
                # BUG FIX: sebelumnya di sini pakai active_numbers.clear() lalu
                # .update(fresh_active) — itu bisa menghapus perubahan yang
                # baru ditulis di memory oleh jalur lain (misalnya notifyMsgIds
                # / lastOTP dari http_otp_handler atau handle_otp_group_message)
                # kalau perubahan itu belum sempat tersimpan ke disk saat file
                # ini dibaca ulang. Sekarang cukup gabungkan: tambah nomor baru
                # yang belum ada, dan buang nomor yang sudah tidak ada di file
                # — tanpa menimpa entry yang sudah ada di memory.
                fresh_active = load_json(ACTIVE_NUMBERS_FILE, {})
                if fresh_active and set(fresh_active.keys()) != set(active_numbers.keys()):
                    changed_by_reload = False
                    for _k, _v in fresh_active.items():
                        if _k not in active_numbers:
                            active_numbers[_k] = _v
                            changed_by_reload = True
                    for _k in list(active_numbers.keys()):
                        if _k not in fresh_active:
                            active_numbers.pop(_k, None)
                            changed_by_reload = True
                    if changed_by_reload:
                        rebuild_suffix_index()

                num_clean = re.sub(r"\D", "", str(number)).lstrip("0")
                # Zed SMS can reuse the same last digits on different country
                # numbers. Do not use the generic suffix matcher here:
                # matching only by suffix can attach a Côte d'Ivoire number
                # to an unrelated Russian active number.
                if ptype == "zedsms":
                    matched = num_clean if num_clean in active_numbers else None
                else:
                    matched = find_active_number(num_clean)
                cc = (
                    active_numbers[matched].get("countryCode", "")
                    if matched and ptype != "zedsms"
                    else guess_cc_from_number(num_clean)
                )

                # Nomor cuma dianggap masih aktif untuk usernya kalau masih
                # ada di daftar yang sedang ditampilkan (sama seperti jalur
                # grup/HTTP) — kalau sudah diganti/expired, jangan kirim ke
                # user itu lagi, tapi tetap teruskan ke grup OTP di bawah.
                if matched and not _number_still_assigned(active_numbers[matched]["userId"], matched):
                    logger.info(f"⏭️ Panel OTP untuk +{matched} tidak dikirim ke user — nomor sudah tidak aktif.")
                    active_numbers.pop(matched, None)
                    rebuild_suffix_index()
                    await async_save_active()
                    matched = None
                    cc = guess_cc_from_number(num_clean)

                # Pengaman tambahan untuk duplicate yang masuk dari dua jalur
                # hampir bersamaan sebelum riwayat sempat tersimpan.
                if _is_duplicate_otp(num_clean, display_otp):
                    logger.info(f"⏭️ Panel row {display_otp} untuk +{num_clean} dobel dalam {OTP_DUPLICATE_WINDOW_SECONDS} detik terakhir, dilewati.")
                    continue

                text, kb = render_otp_message(bn, num_clean, display_otp, svc_id, sms, cc)

                # ── Push ke Live Timeline (admin selalu, user kalau nomor matched) ──
                if otp:
                    asyncio.create_task(record_otp_event(f"panel_{bn}", matched and active_numbers[matched]["userId"], cc, svc_id, num_clean, otp))

                # 1) Kirim ke semua grup OTP yang dikonfigurasi
                await _panel_send_to_groups(app, text, kb)

                # 2) Kirim juga ke user spesifik sesuai nomor di list aktif saat itu
                panel_user_id = None
                panel_earned = 0.0
                if matched and otp:
                    an   = active_numbers[matched]
                    uid  = an["userId"]
                    panel_user_id = uid
                    panel_earned = await add_earning(uid, cc)
                    balance = get_user_earnings(uid)["balance"]

                    user_text, user_kb = render_user_otp_message(
                        bn, matched, otp, svc_id, sms, cc,
                        earned=panel_earned, balance=balance
                    )
                    try:
                        sent_user_msg = await safe_send_message(app.bot, int(uid), user_text, parse_mode="HTML", reply_markup=user_kb)
                        await _track_otp_notify_msg(matched, sent_user_msg.message_id)
                        logger.info(f"✅ OTP sent to user: +{matched} → uid={uid} otp={otp}")
                    except Exception as e:
                        logger.error(f"❌ notify error uid={uid}: {e}")
                else:
                    logger.info(
                        f"ℹ️ Panel row +{num_clean} ({display_otp}) "
                        "hanya dikirim ke grup."
                    )

                # Hidden rows are group-only status rows, not OTP earnings or
                # OTP history entries.
                if otp:
                    otp_log.append({
                        "phoneNumber": num_clean,
                        "userId": panel_user_id,
                        "countryCode": cc,
                        "service": svc_id,
                        "otpCode": otp,
                        "earned": panel_earned,
                        "messageId": None,
                        "delivered": True,
                        "source": f"panel_{bn}",
                        "timestamp": now_wib().isoformat(),
                    })
                    await async_save_otp_log()

                await asyncio.sleep(0.3)  # Telegram rate limit

            await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            otp_panel_status[aid] = "stopped"
            otp_panel_session.pop(aid, None)
            logger.info(f"⏹️ [{bn}] {username} stopped")
            return
        except Exception as e:
            otp_panel_status[aid] = "error"
            logger.error(f"❌ [{bn}] {username} error: {e}")
            alert_type = _classify_panel_error(str(e))
            asyncio.create_task(alert_owner_panel(app, bn, username, alert_type, str(e)))
            session_info = None
            await asyncio.sleep(30)

def start_panel(panel_row, app) -> bool:
    """Start semua akun aktif milik 1 panel. Return True kalau minimal 1 akun jalan."""
    bn = panel_row["name"]
    stop_panel(bn)
    accounts = get_accounts(bn)  # active=1 saja
    if not accounts:
        logger.warning(f"[{bn}] tidak ada akun aktif — dilewati")
        return False
    for acc in accounts:
        otp_panel_tasks[acc["id"]] = asyncio.create_task(run_account(panel_row, acc, app))
    logger.info(f"✅ [{bn}] started {len(accounts)} account(s)")
    return True

def stop_panel(bn: str):
    """Stop semua task akun milik 1 panel (aktif maupun nonaktif)."""
    for acc in get_all_accounts(bn):
        aid = acc["id"]
        t = otp_panel_tasks.get(aid)
        if t and not t.done():
            t.cancel()
        otp_panel_tasks.pop(aid, None)
        otp_panel_session.pop(aid, None)
        otp_panel_status.pop(aid, None)

def is_running(bn: str) -> bool:
    for acc in get_all_accounts(bn):
        t = otp_panel_tasks.get(acc["id"])
        if t and not t.done():
            return True
    return False

def start_all_panels(app):
    rebuild_suffix_index()  # startup এ index তৈরি করো
    count = 0
    for p in get_panels():
        if p["enabled"] and start_panel(p, app):
            count += 1
    logger.info(f"📡 {count} panel(s) started")

# ── Admin Panel Callbacks ──

def kb_panels_home():
    return InlineKeyboardMarkup([
        [mkbtn("a_add_numbers", "Add Panel", callback_data="p:add", style="success"),
         mkbtn("a_cntry_list", "List Panels", callback_data="p:list", style="primary")],
        [mkbtn("a_panel_start", "Start All", callback_data="p:allon", style="success"),
         mkbtn("a_panel_stop", "Stop All", callback_data="p:alloff", style="danger")],
        [mkbtn("a_panel_restart", "Restart All", callback_data="p:restartall", style="success")],
        [mkbtn("a_panel_tmpl_g", "Template Grup", callback_data="panel_template", style="success"),
         mkbtn("a_panel_tmpl_u", "Template User", callback_data="panel_template_user", style="success")],
        [mkbtn("a_otp_test", "Test Tampilan OTP", callback_data="test_otp", style="primary")],
        [mkbtn("a_panel_groups", "Groups", callback_data="panel_groups", style="success")],
        [mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")],
    ])

def kb_panel_list():
    panels = get_panels()
    rows = []
    for p in panels:
        icon = "🟢" if is_running(p["name"]) else ("⚫" if not p["enabled"] else "🔴")
        rows.append([mkbtn("a_otp_panels", f"{p['name']}", callback_data=f"pv:{p['name']}", style="success")])
    rows.append([mkbtn("admin_back", "Back", callback_data="p:back", style="primary")])
    return InlineKeyboardMarkup(rows)

def kb_panel_detail(bn):
    running = is_running(bn)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏹ Stop" if running else "▶ Start", callback_data=f"pd:toggle:{bn}", api_kwargs=_make_btn_kwargs("danger" if running else "success", get_btn_emoji_id("a_panel_stop", "⏹")))],
        [mkbtn("a_add_numbers", "Add Account", callback_data=f"pd:addacc:{bn}", style="success"),
         mkbtn("a_panel_tmpl_u", "Accounts", callback_data=f"pd:accs:{bn}", style="success")],
        [mkbtn("a_delete", "Delete Panel", callback_data=f"pd:del:{bn}", style="danger")],
        [mkbtn("admin_back", "Back", callback_data="p:list", style="primary")],
    ])

def kb_panel_accounts(bn):
    accs = get_all_accounts(bn)
    panel = get_panel(bn)
    ptype = panel["ptype"] if panel else ""
    rows = []
    for a in accs:
        icon = "✅" if a["active"] else "❌"
        interval = _account_poll_interval(ptype, a)
        rows.append([
            mkbtn(
                "a_user_stats",
                f"{a['username']} · {interval}s",
                callback_data="ac:noop",
                style="success",
            ),
            mkbtn("a_delete", "Del", callback_data=f"ac:del:{a['id']}:{bn}", style="danger"),
        ])
    rows.append([mkbtn("a_add_numbers", "Add Account", callback_data=f"pd:addacc:{bn}", style="success")])
    rows.append([mkbtn("admin_back", "Back", callback_data=f"pv:{bn}", style="primary")])
    return InlineKeyboardMarkup(rows)

def kb_builtin_select():
    rows, row = [], []
    for name in sorted(BUILTIN_PANELS.keys()):
        row.append(mkbtn("a_otp_panels", name, callback_data=f"bi:{name}", style="success"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([mkbtn("a_hm_manual", "Custom Panel", callback_data="bi:__custom__", style="success")])
    rows.append([mkbtn("a_confirm_no", "Cancel", callback_data="p:back", style="danger")])
    return InlineKeyboardMarkup(rows)

def kb_ptype():
    rows, row = [], []
    for pt in PANEL_TYPES:
        row.append(mkbtn("a_panel_tmpl_g", pt, callback_data=f"pt:{pt}", style="success"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)

def kb_panel_select_for_account():
    rows = [[mkbtn("a_otp_panels", p["name"], callback_data=f"pd:addacc:{p['name']}", style="success")]
            for p in get_panels()]
    rows.append([mkbtn("a_confirm_no", "Cancel", callback_data="a:back", style="danger")])
    return InlineKeyboardMarkup(rows)

async def cb_admin_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point tombol '📡 OTP Panels' — tampilan & alur input identik dengan SC_jadi."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("📡 <b>OTP Panels</b>", parse_mode="HTML", reply_markup=kb_panels_home())

def _test_otp_service_keyboard() -> InlineKeyboardMarkup:
    """Service picker for the admin-only synthetic OTP preview."""
    rows, row = [], []
    for svc_id, svc in services.items():
        label = f"{svc.get('icon', '📱')} {svc.get('name', svc_id)}"
        row.append(mkbtn("a_otp_test", label, callback_data=f"test_otp_service:{svc_id}", style="success"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([mkbtn("admin_back", "Kembali", callback_data="p:back", style="primary")])
    return InlineKeyboardMarkup(rows)

async def cb_test_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the service picker for a safe, synthetic OTP group preview."""
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only", show_alert=True)
    await query.answer()
    await query.edit_message_text(
        "🧪 <b>Test Tampilan OTP</b>\n\n"
        "Pilih service untuk mengirim contoh ke grup OTP.\n"
        "Nomor dan kode dibuat acak untuk preview saja — tidak berasal dari layanan asli.",
        parse_mode="HTML",
        reply_markup=_test_otp_service_keyboard(),
    )

async def cb_test_otp_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send one clearly marked synthetic OTP using the active group template."""
    query = update.callback_query
    uid = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only", show_alert=True)

    svc_id = query.data.split(":", 1)[1]
    svc = services.get(svc_id)
    if not svc:
        return await query.answer("❌ Service tidak ditemukan", show_alert=True)

    groups = get_otp_groups()
    if not groups:
        return await query.answer(
            "❌ Belum ada grup OTP. Tambahkan grup dulu.",
            show_alert=True,
        )

    await query.answer("⏳ Mengirim preview...")
    # This number is deliberately generated locally and is never requested
    # from, or sent to, a third-party service.
    test_number = "628" + str(random.randint(100000000, 999999999))
    test_otp = f"{random.randint(0, 999999):06d}"
    service_name = str(svc.get("name", svc_id))
    test_sms = f"{service_name} test verification code: {test_otp}"

    text, kb = render_otp_message(
        "TEST MODE",
        test_number,
        test_otp,
        svc_id,
        test_sms,
        "62",
    )
    text = (
        "🧪 <b>TEST OTP — DATA SINTETIS / BUKAN OTP ASLI</b>\n\n"
        + text
    )

    await _panel_send_to_groups(context.application, text, kb)
    await query.edit_message_text(
        f"✅ <b>Preview terkirim</b>\n\n"
        f"{html.escape(service_name)}\n"
        f"Nomor sintetis: <code>+{test_number}</code>\n"
        f"Kode sintetis: <code>{test_otp}</code>\n\n"
        "Pesan diberi label TEST agar tidak tertukar dengan OTP produksi.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [mkbtn("a_otp_test", "Test Service Lain", callback_data="test_otp", style="primary")],
            [mkbtn("admin_back", "Kembali", callback_data="p:back", style="primary")],
        ]),
    )

async def cb_p_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("📡 <b>OTP Panels</b>", parse_mode="HTML", reply_markup=kb_panels_home())

async def cb_p_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    panels = get_panels()
    txt = "📋 Select a panel:" if panels else "Belum ada panel.\nTambah dulu dengan ➕"
    kb  = kb_panel_list() if panels else kb_panels_home()
    await query.edit_message_text(txt, reply_markup=kb)

async def cb_p_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➕ Select panel to add:", reply_markup=kb_builtin_select())

async def cb_p_allon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    count = 0
    for p in get_panels():
        with db_conn() as c:
            c.execute("UPDATE panels SET enabled=1 WHERE name=?", (p["name"],))
        p2 = get_panel(p["name"])
        if start_panel(p2, context.application):
            count += 1
    await query.edit_message_text(f"✅ Started <b>{count}</b> panels.", parse_mode="HTML", reply_markup=kb_panels_home())

async def cb_p_alloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    for p in get_panels():
        stop_panel(p["name"])
        with db_conn() as c:
            c.execute("UPDATE panels SET enabled=0 WHERE name=?", (p["name"],))
    await query.edit_message_text("⏹ All panels stopped.", reply_markup=kb_panels_home())

async def cb_p_restartall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Restarting...")
    count = 0
    for p in get_panels():
        if p["enabled"]:
            stop_panel(p["name"])
            if start_panel(p, context.application):
                count += 1
    await query.edit_message_text(f"✅ <b>{count}</b> panel(s) restarted!", parse_mode="HTML", reply_markup=kb_panels_home())

async def cb_bi_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pilih panel bawaan (builtin) atau custom — persis alur SC_jadi."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    name = query.data[3:]
    if name == "__custom__":
        get_session(uid)["state"] = "sc_panel_wizard"
        get_session(uid)["data"]  = {"action": "add_custom"}
        await query.edit_message_text("✏️ Enter panel <b>name</b>:", parse_mode="HTML")
    else:
        bp = BUILTIN_PANELS[name]
        get_session(uid)["state"] = "sc_panel_wizard"
        get_session(uid)["data"]  = {
            "action": "add_builtin", "panel_name": name,
            "url": bp["url"], "ptype": bp["ptype"], "fp": bp.get("fp"),
        }
        account_label = "account name" if _panel_uses_api_token(bp["ptype"]) else "username"
        await query.edit_message_text(
            f"📌 <b>{name}</b>\n\nEnter <b>{account_label}</b>:",
            parse_mode="HTML",
        )

async def cb_pt_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pilih tipe panel untuk custom panel."""
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    ptype = query.data[3:]
    st = get_session(uid).get("data") or {}
    st["ptype"]  = ptype
    st["fp"]     = None
    st["action"] = "add_builtin"
    get_session(uid)["data"]  = st
    get_session(uid)["state"] = "sc_panel_wizard"
    account_label = "account name" if _panel_uses_api_token(ptype) else "username"
    await query.edit_message_text(
        f"Type: <b>{ptype}</b> ✅\n\nEnter <b>{account_label}</b>:",
        parse_mode="HTML",
    )

async def cb_pv_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bn = query.data[3:]
    p  = get_panel(bn)
    if not p:
        await query.edit_message_text("Panel not found."); return
    accs    = get_accounts(bn)
    running = is_running(bn)
    status  = "🟢 Running" if running else ("⚫ Stopped" if p["enabled"] else "🔴 Disabled")
    await query.edit_message_text(
        f"📌 <b>{bn}</b>\n"
        f"Status : {status}\n"
        f"Type   : <b>{PANEL_TYPE_LABEL.get(p['ptype'], p['ptype'])}</b>\n"
        f"URL    : <code>{p['url']}</code>\n"
        f"Accounts: {len(accs)} active",
        parse_mode="HTML", reply_markup=kb_panel_detail(bn))

async def cb_pd_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    _, action, bn = query.data.split(":", 2)

    if action == "toggle":
        if is_running(bn):
            stop_panel(bn)
            with db_conn() as c:
                c.execute("UPDATE panels SET enabled=0 WHERE name=?", (bn,))
            msg = f"⏹ <b>{bn}</b> stopped."
        else:
            with db_conn() as c:
                c.execute("UPDATE panels SET enabled=1 WHERE name=?", (bn,))
            p  = get_panel(bn)
            ok = start_panel(p, context.application)
            msg = f"✅ <b>{bn}</b> started." if ok else f"⚠️ <b>{bn}</b>: no accounts — add one first!"
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb_panel_detail(bn))

    elif action == "del":
        stop_panel(bn)
        with db_conn() as c:
            c.execute("DELETE FROM accounts WHERE panel_name=?", (bn,))
            c.execute("DELETE FROM panels WHERE name=?", (bn,))
        panels = get_panels()
        kb  = kb_panel_list() if panels else kb_panels_home()
        await query.edit_message_text(f"🗑 <b>{bn}</b> deleted.", parse_mode="HTML", reply_markup=kb)

    elif action == "addacc":
        get_session(uid)["state"] = "sc_panel_wizard"
        get_session(uid)["data"]  = {"action": "add_account", "panel_name": bn}
        panel = get_panel(bn)
        account_label = "account name" if panel and _panel_uses_api_token(panel["ptype"]) else "username"
        await query.edit_message_text(
            f"➕ Add account to <b>{bn}</b>\n\nEnter <b>{account_label}</b>:",
            parse_mode="HTML",
        )

    elif action == "accs":
        await query.edit_message_text(f"👤 Accounts — <b>{bn}</b>:", parse_mode="HTML", reply_markup=kb_panel_accounts(bn))

async def cb_ac_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts  = query.data.split(":")
    action = parts[1]
    if action == "noop":
        return
    if action == "del":
        acc_id = int(parts[2])
        bn     = parts[3]
        t = otp_panel_tasks.get(acc_id)
        if t and not t.done():
            t.cancel()
        otp_panel_tasks.pop(acc_id, None)
        otp_panel_session.pop(acc_id, None)
        otp_panel_status.pop(acc_id, None)
        with db_conn() as c:
            c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
        await query.edit_message_text(f"🗑 Account removed from <b>{bn}</b>.", parse_mode="HTML",
                                       reply_markup=kb_panel_accounts(bn))

async def cb_a_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    panels = get_panels()
    if not panels:
        await query.edit_message_text("Belum ada panel.", reply_markup=kb_panels_home()); return
    rows = []
    for p in panels:
        n = len(get_all_accounts(p["name"]))
        rows.append([mkbtn("a_otp_panels", f"📌 {p['name']}", callback_data=f"pd:accs:{p['name']}", style="success", auto_icon=False)])
    rows.append([mkbtn("admin_back", "Back", callback_data="a:back", style="primary")])
    await query.edit_message_text("👤 Select panel:", reply_markup=InlineKeyboardMarkup(rows))

async def cb_a_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    panels = get_panels()
    if not panels:
        await query.edit_message_text("Belum ada panel. Tambah panel dulu.", reply_markup=kb_panels_home()); return
    await query.edit_message_text("Select panel to add account to:", reply_markup=kb_panel_select_for_account())

async def cb_a_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = None
    get_session(uid)["data"]  = None
    await query.edit_message_text("📡 <b>OTP Panels</b>", parse_mode="HTML", reply_markup=kb_panels_home())

async def cb_admin_global_wa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    if not get_session(uid)["is_admin"] and not is_admin(uid):
        return await query.answer("❌ Admin only")
    await query.answer()

    connected = global_wa_data.get("connected", False)
    enabled   = global_wa_data.get("enabled", False)
    phone     = global_wa_data.get("phone", "N/A")

    status_icon = "🟢" if connected else "🔴"
    toggle_icon = "✅ ON" if enabled else "❌ OFF"

    msg = (
        f"📱 <b>Global WhatsApp System</b>\n\n"
        f"<b>Status:</b> {status_icon} {'Connected' if connected else 'Disconnected'}\n"
        f"<b>Phone:</b> `{phone}`\n"
        f"<b>WA Check:</b> {toggle_icon}\n\n"
        f"Connect a WhatsApp to check all user numbers automatically."
    )

    buttons = []
    if connected:
        buttons.append([
            InlineKeyboardButton(f"{'🔴 Disable' if enabled else '🟢 Enable'} WA Check", callback_data="global_wa_toggle", api_kwargs=_make_btn_kwargs("success" if not enabled else "danger", get_btn_emoji_id("wa_status", "📊"))),
            mkbtn("wa_disconnect", "Disconnect", callback_data="global_wa_disconnect", style="danger")
        ])
    else:
        buttons.append([mkbtn("wa_connect", "Connect WhatsApp", callback_data="global_wa_connect", style="success")])

    buttons.append([mkbtn("admin_back", "Back", callback_data="admin_back", style="primary")])
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cb_global_wa_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "global_wa_phone"
    await query.edit_message_text(
        "📱 <b>Global WhatsApp Connect</b>\n\n"
        "Enter WhatsApp number (with country code):\n"
        "Example: <code>8801712345678</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            mkbtn("a_confirm_no", "Cancel", callback_data="admin_global_wa", style="danger")
        ]])
    )

async def cb_global_wa_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global_wa_data["enabled"] = not global_wa_data.get("enabled", False)
    save_global_wa()
    status = "✅ Enabled" if global_wa_data["enabled"] else "❌ Disabled"
    await query.answer(f"Global WA Check {status}", show_alert=True)
    await cb_admin_global_wa(update, context)

async def cb_global_wa_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    wa_uid = global_wa_data.get("uid", "")
    if wa_uid and wa_uid in wa_sessions:
        wa_sessions.pop(wa_uid, None)
    global_wa_data["connected"] = False
    global_wa_data["phone"]     = ""
    global_wa_data["enabled"]   = False
    save_global_wa()
    await query.answer("🔌 Global WA Disconnected", show_alert=True)
    await cb_admin_global_wa(update, context)

# ─── Groups (grup tujuan kirim OTP) ───

async def cb_panel_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    groups = get_otp_groups()
    msg = f"👥 <b>OTP Groups</b>\n\nOTP dari semua panel akan dikirim ke grup-grup ini.\n\nTotal: *{len(groups)}*\n\n"
    for i, g in enumerate(groups):
        msg += f"<b>{i+1}.</b> `{g}`\n"
    if not groups:
        msg += "<i>Belum ada grup.</i>\n"
    buttons = [
        [mkbtn("a_add_numbers", "Add Group", callback_data="panel_group_add", style="success")],
    ]
    if groups:
        buttons.append([mkbtn("a_delete", "Remove Group", callback_data="panel_group_del", style="success")])
    buttons.append([mkbtn("admin_back", "Back", callback_data="admin_panels", style="primary")])
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cb_panel_group_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_add_otp_group"
    await query.edit_message_text(
        "➕ <b>Add OTP Group</b>\n\n"
        "Kirim <b>chat ID</b> grup tujuan (angka negatif, contoh: <code>-1001234567890</code>).\n\n"
        "Tips: forward pesan apa saja dari grup itu ke @userinfobot atau bot serupa untuk lihat chat ID-nya, "
        "atau invite bot ini ke grup lalu kirim <code>/id</code> di grup itu.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            mkbtn("a_confirm_no", "Cancel", callback_data="panel_groups", style="danger")
        ]])
    )

async def cb_panel_group_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    groups = get_otp_groups()
    if not groups:
        return await query.edit_message_text("❌ Belum ada grup.",
            reply_markup=InlineKeyboardMarkup([[mkbtn("admin_back", "Back", callback_data="panel_groups", style="primary")]]))
    buttons = [[mkbtn("a_delete", f"🗑️ {g}", callback_data=f"panel_group_del_confirm:{g}", style="success", auto_icon=False)] for g in groups]
    buttons.append([mkbtn("admin_back", "Back", callback_data="panel_groups", style="primary")])
    await query.edit_message_text("🗑️ <b>Grup mana yang mau dihapus?</b>", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_panel_group_del_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = query.data.split(":", 1)[1]
    remove_otp_group(gid)
    await query.edit_message_text(f"✅ <b>Grup `{gid}` dihapus.</b>", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[mkbtn("admin_back", "Back", callback_data="panel_groups", style="primary")]]))

# ─── Template (format pesan OTP) ───

async def cb_panel_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tmpl = get_otp_template()
    preview_text, preview_kb = render_otp_message(
        "ContohPanel", "8801712345678", "123456", "whatsapp",
        "WhatsApp code: 123-456", "880"
    )
    raw = json.dumps(tmpl, ensure_ascii=False, indent=2)
    cur_name = tmpl.get("name", "Custom")
    msg = (
        "🎨 <b>OTP Message Template — GRUP</b>\n\n"
        "Ini format pesan OTP yang dikirim ke <b>grup</b>.\n"
        f"Template aktif: <b>{cur_name}</b>\n\n"
        "Template JSON saat ini:\n"
        f"```\n{raw}\n```\n\n"
        "<b>Placeholder tersedia:</b>\n"
        "`{flag}<code> </code>{flang}<code> </code>{country}<code> </code>{number}<code> </code>{number_masked}<code> </code>{prefix}<code> </code>{otp}` "
        "`{service}<code> </code>{svc_icon}<code> </code>{panel}<code> </code>{message}<code> </code>{time}`\n"
        "`{iso}<code> </code>{flag_plain}<code> </code>{country_tag}<code> </code>{svc_short}<code> </code>{sender}` "
        "`{language}<code> </code>{lang_full}`\n"
        "🫥 <b>{prefix}</b> (atau <b>:Prefix</b>) menampilkan 6 digit pertama nomor sebagai spoiler Telegram; ketuk untuk melihatnya.\n\n"
        "Pilih salah satu preset di bawah, atau buat custom sendiri 👇"
    )
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [mkbtn("a_panel_tmpl_g", f"1️⃣ {GROUP_TEMPLATE_PRESETS['1']['name']}", callback_data="panel_template_preset:1", style="success"),
         mkbtn("a_panel_tmpl_g", f"2️⃣ {GROUP_TEMPLATE_PRESETS['2']['name']}", callback_data="panel_template_preset:2", style="success"),
         mkbtn("a_panel_tmpl_g", f"3️⃣ {GROUP_TEMPLATE_PRESETS['3']['name']}", callback_data="panel_template_preset:3", style="success")],
        [mkbtn("a_hm_manual", "Edit / Custom", callback_data="panel_template_edit", style="success")],
        [mkbtn("admin_back", "Back", callback_data="admin_panels", style="primary")],
    ]))
    try:
        await context.bot.send_message(
            update.effective_chat.id, preview_text, parse_mode="HTML", reply_markup=preview_kb
        )
    except Exception as e:
        logger.error(f"template preview error: {e}")

async def cb_panel_template_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    preset = GROUP_TEMPLATE_PRESETS.get(key)
    if not preset:
        await query.answer("❌ Preset tidak ditemukan", show_alert=True)
        return
    await query.answer(f"✅ Preset '{preset['name']}' diterapkan")
    set_otp_template(preset)
    await cb_panel_template(update, context)

async def cb_panel_template_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_edit_otp_template"
    tmpl = get_otp_template()
    raw  = json.dumps(tmpl, ensure_ascii=False, indent=2)
    await query.edit_message_text(
        "✏️ <b>Edit Template Grup</b>\n\n"
        "Kirim template baru dalam format JSON, contoh:\n"
        f"```\n{raw}\n```\n\n"
        "Format button <code>type</code>: <code>copy</code> (copy OTP), <code>link</code> (buka URL), <code>sep</code> (baris baru).\n"
        "Warna tombol pakai key <code>style</code>: <code>primary</code>, <code>success</code> (hijau, default), atau <code>danger</code>.\n"
        "Icon di tombol <code>copy</code> disembunyikan otomatis; tambahkan <code>\"icon\": true</code> pada tombolnya kalau tetap mau menampilkan icon.\n"
        "Gunakan `{flag}<code> </code>{flang}`, `{prefix}` untuk 6 digit awal yang tersembunyi, dan `{e1}<code>–</code>{e5}` untuk emoji kustom (atur di 🎨 Custom Emoji → Template).\n\n"
        "💎 <b>Emoji Premium:</b> kalau kamu paste emoji Custom Emoji Telegram Premium langsung di teks atau label tombol, ID-nya otomatis kebaca & dipasang saat disimpan — emoji itu tetap tampil dengan desain aslinya buat semua user.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            mkbtn("a_confirm_no", "Cancel", callback_data="panel_template", style="danger")
        ]])
    )

async def cb_panel_template_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("♻️ Reset ke default")
    set_otp_template(DEFAULT_OTP_TEMPLATE)
    await cb_panel_template(update, context)

# ── Template User (chat pribadi) — terpisah dari template grup ──

async def cb_panel_template_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tmpl = get_otp_user_template()
    preview_text, preview_kb = render_user_otp_message(
        "ContohPanel", "8801712345678", "123456", "whatsapp",
        "WhatsApp code: 123-456", "880", earned=0.05, balance=1.25
    )
    raw = json.dumps(tmpl, ensure_ascii=False, indent=2)
    cur_name = tmpl.get("name", "Custom")
    msg = (
        "👤 <b>OTP Message Template — USER</b>\n\n"
        "Ini format pesan OTP yang dikirim ke <b>chat pribadi user</b> (beda dari template grup).\n"
        f"Template aktif: <b>{cur_name}</b>\n\n"
        "Template JSON saat ini:\n"
        f"```\n{raw}\n```\n\n"
        "<b>Placeholder tersedia:</b>\n"
        "`{flag}<code> </code>{flang}<code> </code>{country}<code> </code>{number}<code> </code>{number_masked}<code> </code>{prefix}<code> </code>{otp}` "
        "`{service}<code> </code>{svc_icon}<code> </code>{panel}<code> </code>{message}<code> </code>{time}` "
        "`{earned}<code> </code>{balance}`\n"
        "`{iso}<code> </code>{flag_plain}<code> </code>{country_tag}<code> </code>{svc_short}<code> </code>{sender}` "
        "`{language}<code> </code>{lang_full}`\n"
        "🫥 <b>{prefix}</b> (atau <b>:Prefix</b>) adalah 6 digit awal nomor dalam spoiler Telegram (ketuk untuk melihat).\n"
        "`{e1}<code> </code>{e2}<code> </code>{e3}<code> </code>{e4}<code> </code>{e5}` <i>(emoji kustom, atur di Custom Emoji → Template)</i>\n\n"
        "Pilih salah satu preset di bawah, atau buat custom sendiri 👇"
    )
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [mkbtn("a_panel_tmpl_u", f"1️⃣ {USER_TEMPLATE_PRESETS['1']['name']}", callback_data="panel_template_user_preset:1", style="success"),
         mkbtn("a_panel_tmpl_u", f"2️⃣ {USER_TEMPLATE_PRESETS['2']['name']}", callback_data="panel_template_user_preset:2", style="success"),
         mkbtn("a_panel_tmpl_u", f"3️⃣ {USER_TEMPLATE_PRESETS['3']['name']}", callback_data="panel_template_user_preset:3", style="success")],
        [mkbtn("a_hm_manual", "Edit / Custom", callback_data="panel_template_user_edit", style="success")],
        [mkbtn("admin_back", "Back", callback_data="admin_panels", style="primary")],
    ]))
    try:
        await context.bot.send_message(
            update.effective_chat.id, preview_text, parse_mode="HTML", reply_markup=preview_kb
        )
    except Exception as e:
        logger.error(f"user template preview error: {e}")

async def cb_panel_template_user_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = query.data.split(":", 1)[1]
    preset = USER_TEMPLATE_PRESETS.get(key)
    if not preset:
        await query.answer("❌ Preset tidak ditemukan", show_alert=True)
        return
    await query.answer(f"✅ Preset '{preset['name']}' diterapkan")
    set_otp_user_template(preset)
    await cb_panel_template_user(update, context)

async def cb_panel_template_user_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(update.effective_user.id)
    await query.answer()
    get_session(uid)["state"] = "admin_edit_otp_user_template"
    tmpl = get_otp_user_template()
    raw  = json.dumps(tmpl, ensure_ascii=False, indent=2)
    await query.edit_message_text(
        "✏️ <b>Edit Template User</b>\n\n"
        "Kirim template baru dalam format JSON, contoh:\n"
        f"```\n{raw}\n```\n\n"
        "Extra placeholder khusus user: `{earned}<code>, </code>{balance}`.\n"
        "Gunakan `{flag}<code> </code>{flang}`, `{prefix}` untuk 6 digit awal yang tersembunyi, dan `{e1}<code>–</code>{e5}` untuk emoji kustom (atur di Custom Emoji → Template).\n"
        "Format button <code>type</code>: <code>copy</code> (copy OTP), <code>link</code> (buka URL), <code>sep</code> (baris baru).\n"
        "Warna tombol pakai key <code>style</code>: <code>primary</code>, <code>success</code> (hijau, default), atau <code>danger</code>.\n"
        "Icon di tombol <code>copy</code> disembunyikan otomatis; tambahkan <code>\"icon\": true</code> pada tombolnya kalau tetap mau menampilkan icon.\n\n"
        "💎 <b>Emoji Premium:</b> kalau kamu paste emoji Custom Emoji Telegram Premium langsung di teks atau label tombol, ID-nya otomatis kebaca & dipasang saat disimpan — emoji itu tetap tampil dengan desain aslinya buat semua user.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            mkbtn("a_confirm_no", "Cancel", callback_data="panel_template_user", style="danger")
        ]])
    )

async def cb_panel_template_user_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("♻️ Reset ke default")
    set_otp_user_template(DEFAULT_USER_OTP_TEMPLATE)
    await cb_panel_template_user(update, context)

# ─── Main ───
def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN belum diatur. Set environment variable BOT_TOKEN "
            "(atau TELEGRAM_BOT_TOKEN) sebelum menjalankan bot."
        )
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("otp", cmd_otp))
    app.add_handler(CommandHandler("menu", cmd_menu))


    # EN + ID button text patterns
    # NOTE: Tombol menu utama (Get Number/Get File/Search OTP/Live Traffic/Tools/
    # Profile/Support) SENGAJA tidak lagi didaftarkan sebagai MessageHandler
    # filters.Regex hardcoded di sini — karena teksnya sekarang dinamis
    # (emoji-nya ikut custom emoji admin, teksnya ikut bahasa user). Semua
    # tombol itu sudah ditangani secara dinamis oleh handle_text() lewat
    # reply_menu_labels() + MENU_HANDLERS di atas, jadi selalu cocok berapa
    # pun emoji/bahasanya berubah.
    app.add_handler(CallbackQueryHandler(cb_user_live_traffic, pattern="^user_live_traffic$"))
    app.add_handler(CallbackQueryHandler(cb_livetimeline_stop, pattern="^livetimeline_stop$"))
    app.add_handler(CallbackQueryHandler(cb_admin_live_timeline, pattern="^admin_live_timeline$"))
    app.add_handler(CallbackQueryHandler(cb_admin_live_timeline_stop, pattern="^admin_livetimeline_stop$"))
    app.add_handler(MessageHandler(filters.Regex("^📧"), handle_tempmail))
    app.add_handler(MessageHandler(filters.Regex("^🔐"), handle_2fa))
    app.add_handler(MessageHandler(filters.Regex("^💰 Balances$"), handle_balance))
    app.add_handler(MessageHandler(filters.Regex("^💸 Withdraw$"), handle_withdraw))
    app.add_handler(MessageHandler(filters.Regex("^👥 Referral$"), handle_referral))
    app.add_handler(CallbackQueryHandler(cb_tools_tempmail, pattern="^tools_tempmail$"))
    app.add_handler(CallbackQueryHandler(cb_tools_2fa, pattern="^tools_2fa$"))
    app.add_handler(CallbackQueryHandler(cb_profil_balance, pattern="^profil_balance$"))
    app.add_handler(CallbackQueryHandler(cb_profil_withdraw, pattern="^profil_withdraw$"))
    app.add_handler(CallbackQueryHandler(cb_profil_referral, pattern="^profil_referral$"))

    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))

    app.add_handler(CallbackQueryHandler(cb_verify, pattern="^verify_user$"))
    app.add_handler(CallbackQueryHandler(cb_select_service, pattern="^svc:"))
    app.add_handler(CallbackQueryHandler(cb_select_country, pattern="^cc:"))
    app.add_handler(CallbackQueryHandler(cb_new_numbers, pattern="^newnum:"))
    app.add_handler(CallbackQueryHandler(cb_back_services, pattern="^back_services$"))
    app.add_handler(CallbackQueryHandler(cb_select_service_file, pattern="^filesvc:"))
    app.add_handler(CallbackQueryHandler(cb_select_country_file, pattern="^filecc:"))
    app.add_handler(CallbackQueryHandler(cb_new_file, pattern="^filenew:"))
    app.add_handler(CallbackQueryHandler(cb_back_services_file, pattern="^fileback_services$"))

    app.add_handler(CallbackQueryHandler(cb_start_withdraw, pattern="^start_withdraw$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_method, pattern="^wm:"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_amount, pattern="^wa:"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_cancel, pattern="^w_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_confirm, pattern="^w_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_history, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(cb_goto_main, pattern="^goto_main$"))

    app.add_handler(CallbackQueryHandler(cb_wa_connect, pattern="^wa_connect$"))
    app.add_handler(CallbackQueryHandler(cb_wa_status, pattern="^wa_status$"))
    app.add_handler(CallbackQueryHandler(cb_wa_disconnect, pattern="^wa_disconnect$"))

    app.add_handler(CallbackQueryHandler(cb_tm_create, pattern="^tm_create$"))
    app.add_handler(CallbackQueryHandler(cb_tm_inbox, pattern="^tm_inbox$"))
    app.add_handler(CallbackQueryHandler(cb_tm_show, pattern="^tm_show$"))
    app.add_handler(CallbackQueryHandler(cb_tm_delete, pattern="^tm_delete$"))

    app.add_handler(CallbackQueryHandler(cb_totp_service, pattern="^totp:"))
    app.add_handler(CallbackQueryHandler(cb_totp_back, pattern="^totp_back$"))
    app.add_handler(CallbackQueryHandler(cb_totp_refresh, pattern="^totp_r:"))

    app.add_handler(CallbackQueryHandler(cb_ref_stats, pattern="^ref_stats$"))

    app.add_handler(CallbackQueryHandler(cb_admin_stock, pattern="^admin_stock$"))
    app.add_handler(CallbackQueryHandler(cb_admin_live_traffic, pattern="^admin_live_traffic$"))
    app.add_handler(CallbackQueryHandler(cb_admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(cb_admin_otp_log, pattern="^admin_otp_log$"))
    app.add_handler(CallbackQueryHandler(cb_admin_dashboard, pattern="^admin_dashboard$"))
    app.add_handler(CallbackQueryHandler(cb_dash_hourly, pattern="^dash_hourly$"))
    app.add_handler(CallbackQueryHandler(cb_dash_daily, pattern="^dash_daily$"))
    app.add_handler(CallbackQueryHandler(cb_dash_monthly, pattern="^dash_monthly$"))
    app.add_handler(CallbackQueryHandler(cb_dash_growth, pattern="^dash_growth$"))
    app.add_handler(CallbackQueryHandler(cb_dash_panels, pattern="^dash_panels$"))
    app.add_handler(CallbackQueryHandler(cb_dash_countries, pattern="^dash_countries$"))
    app.add_handler(CallbackQueryHandler(cb_dash_apps, pattern="^dash_apps$"))
    app.add_handler(CallbackQueryHandler(cb_admin_broadcast, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(cb_admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(cb_admin_toggle_verify, pattern="^as_toggle_verify$"))
    app.add_handler(CallbackQueryHandler(cb_admin_toggle_withdraw, pattern="^as_toggle_withdraw$"))
    app.add_handler(CallbackQueryHandler(cb_admin_toggle_stocknotify, pattern="^as_toggle_stocknotify$"))
    app.add_handler(CallbackQueryHandler(cb_admin_toggle_countbtn, pattern="^as_toggle_countbtn$"))
    app.add_handler(CallbackQueryHandler(cb_lang_switch, pattern="^lang_switch$"))
    app.add_handler(CallbackQueryHandler(cb_set_lang, pattern="^set_lang:"))
    app.add_handler(CallbackQueryHandler(cb_back_to_profile, pattern="^back_to_profile$"))
    app.add_handler(CallbackQueryHandler(cb_admin_features, pattern="^admin_features$"))
    app.add_handler(CallbackQueryHandler(cb_feat_toggle, pattern="^feat_toggle:"))
    app.add_handler(CallbackQueryHandler(cb_as_count, pattern="^as_count$"))
    app.add_handler(CallbackQueryHandler(cb_as_cooldown, pattern="^as_cooldown$"))
    app.add_handler(CallbackQueryHandler(cb_as_price, pattern="^as_price$"))
    app.add_handler(CallbackQueryHandler(cb_as_minw, pattern="^as_minw$"))
    app.add_handler(CallbackQueryHandler(cb_as_otpwindow, pattern="^as_otpwindow$"))
    app.add_handler(CallbackQueryHandler(cb_as_otpscope, pattern="^as_otpscope$"))
    app.add_handler(CallbackQueryHandler(cb_as_autodelete, pattern="^as_autodelete$"))
    app.add_handler(CallbackQueryHandler(cb_as_toggle_autodelete, pattern="^as_toggle_autodelete$"))
    app.add_handler(CallbackQueryHandler(cb_autodelete_preset, pattern="^ad_preset:"))
    app.add_handler(CallbackQueryHandler(cb_cariotp_cancel, pattern="^cariotp_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_cariotp_again, pattern="^cariotp_again$"))
    app.add_handler(CallbackQueryHandler(cb_as_referral_commission, pattern="^as_referral_commission$"))
    app.add_handler(CallbackQueryHandler(cb_as_set_cek_bio_url, pattern="^as_set_cek_bio_url$"))
    app.add_handler(CallbackQueryHandler(cb_as_set_fix_merah_url, pattern="^as_set_fix_merah_url$"))
    app.add_handler(CallbackQueryHandler(cb_as_set_hidden_mask, pattern="^as_set_hidden_mask$"))
    app.add_handler(CallbackQueryHandler(cb_hidden_mask_digit,  pattern="^hmd:"))
    app.add_handler(CallbackQueryHandler(cb_hidden_mask_preset, pattern="^hm:"))
    app.add_handler(CallbackQueryHandler(cb_admin_referral_stats, pattern="^admin_referral_stats$"))
    app.add_handler(CallbackQueryHandler(cb_admin_add_numbers, pattern="^admin_add_numbers$"))
    app.add_handler(CallbackQueryHandler(cb_admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_approve, pattern="^wadm_approve:"))
    app.add_handler(CallbackQueryHandler(cb_withdraw_reject, pattern="^wadm_reject:"))
    app.add_handler(CallbackQueryHandler(cb_admin_balance_manage, pattern="^admin_balance_manage$"))
    app.add_handler(CallbackQueryHandler(cb_bal_add, pattern="^bal_add$"))
    app.add_handler(CallbackQueryHandler(cb_bal_deduct, pattern="^bal_deduct$"))
    app.add_handler(CallbackQueryHandler(cb_bal_reset, pattern="^bal_reset$"))
    app.add_handler(CallbackQueryHandler(cb_admin_country_prices, pattern="^admin_country_prices$"))
    app.add_handler(CallbackQueryHandler(cb_admin_manage_countries, pattern="^admin_manage_countries$"))
    app.add_handler(CallbackQueryHandler(cb_country_list, pattern="^country_list$"))
    app.add_handler(CallbackQueryHandler(cb_country_add, pattern="^country_add$"))
    app.add_handler(CallbackQueryHandler(cb_admin_manage_services, pattern="^admin_manage_services$"))
    app.add_handler(CallbackQueryHandler(cb_svc_list, pattern="^svc_list$"))
    app.add_handler(CallbackQueryHandler(cb_svc_add, pattern="^svc_add$"))
    app.add_handler(CallbackQueryHandler(cb_admin_upload, pattern="^admin_upload$"))
    app.add_handler(CallbackQueryHandler(cb_upload_svc, pattern="^upload_svc:"))
    app.add_handler(CallbackQueryHandler(cb_admin_delete, pattern="^admin_delete$"))
    app.add_handler(CallbackQueryHandler(cb_del_confirm, pattern="^del_confirm:"))
    app.add_handler(CallbackQueryHandler(cb_del_exec, pattern="^del_exec:"))
    app.add_handler(CallbackQueryHandler(cb_admin_back, pattern="^admin_back$"))
    app.add_handler(CallbackQueryHandler(cb_admin_cancel, pattern="^admin_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_admin_logout, pattern="^admin_logout$"))

    # ─── Custom Emoji Handlers (rebuilt, SQLite-backed) ───
    app.add_handler(CallbackQueryHandler(cb_admin_custom_emoji,   pattern="^admin_custom_emoji$"))
    app.add_handler(CallbackQueryHandler(cb_show_bottom_menu,      pattern="^show_bottom_menu$"))
    app.add_handler(CallbackQueryHandler(cb_emoji_cat,            pattern="^emoji_cat:"))
    app.add_handler(CallbackQueryHandler(cb_emoji_cat_page,       pattern="^emoji_cat_page:"))
    app.add_handler(CallbackQueryHandler(cb_emoji_slot,           pattern="^emoji_slot:"))
    app.add_handler(CallbackQueryHandler(cb_emoji_cat_back,       pattern="^emoji_cat_back$"))
    app.add_handler(CallbackQueryHandler(cb_emoji_reset_all,      pattern="^emoji_reset_all$"))
    app.add_handler(CallbackQueryHandler(cb_view_premium_emoji,   pattern="^view_premium_emoji$"))

    app.add_handler(CallbackQueryHandler(cb_admin_global_wa, pattern="^admin_global_wa$"))
    app.add_handler(CallbackQueryHandler(cb_global_wa_connect, pattern="^global_wa_connect$"))
    app.add_handler(CallbackQueryHandler(cb_global_wa_toggle, pattern="^global_wa_toggle$"))
    app.add_handler(CallbackQueryHandler(cb_global_wa_disconnect, pattern="^global_wa_disconnect$"))
    app.add_handler(CallbackQueryHandler(cb_admin_panels, pattern="^admin_panels$"))
    app.add_handler(CallbackQueryHandler(cb_test_otp, pattern="^test_otp$"))
    app.add_handler(CallbackQueryHandler(cb_test_otp_service, pattern="^test_otp_service:"))
    app.add_handler(CallbackQueryHandler(cb_p_back, pattern="^p:back$"))
    app.add_handler(CallbackQueryHandler(cb_p_list, pattern="^p:list$"))
    app.add_handler(CallbackQueryHandler(cb_p_add, pattern="^p:add$"))
    app.add_handler(CallbackQueryHandler(cb_p_allon, pattern="^p:allon$"))
    app.add_handler(CallbackQueryHandler(cb_p_alloff, pattern="^p:alloff$"))
    app.add_handler(CallbackQueryHandler(cb_p_restartall, pattern="^p:restartall$"))
    app.add_handler(CallbackQueryHandler(cb_bi_select, pattern="^bi:"))
    app.add_handler(CallbackQueryHandler(cb_pt_select, pattern="^pt:"))
    app.add_handler(CallbackQueryHandler(cb_pv_detail, pattern="^pv:"))
    app.add_handler(CallbackQueryHandler(cb_pd_action, pattern="^pd:"))
    app.add_handler(CallbackQueryHandler(cb_ac_action, pattern="^ac:"))
    app.add_handler(CallbackQueryHandler(cb_a_list, pattern="^a:list$"))
    app.add_handler(CallbackQueryHandler(cb_a_add, pattern="^a:add$"))
    app.add_handler(CallbackQueryHandler(cb_a_back, pattern="^a:back$"))
    app.add_handler(CallbackQueryHandler(cb_panel_groups, pattern="^panel_groups$"))
    app.add_handler(CallbackQueryHandler(cb_panel_group_add, pattern="^panel_group_add$"))
    app.add_handler(CallbackQueryHandler(cb_panel_group_del, pattern="^panel_group_del$"))
    app.add_handler(CallbackQueryHandler(cb_panel_group_del_confirm, pattern="^panel_group_del_confirm:"))
    app.add_handler(CallbackQueryHandler(cb_panel_template, pattern="^panel_template$"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_edit, pattern="^panel_template_edit$"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_reset, pattern="^panel_template_reset$"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_preset, pattern="^panel_template_preset:"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_user, pattern="^panel_template_user$"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_user_edit, pattern="^panel_template_user_edit$"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_user_reset, pattern="^panel_template_user_reset$"))
    app.add_handler(CallbackQueryHandler(cb_panel_template_user_preset, pattern="^panel_template_user_preset:"))

    app.add_handler(MessageHandler(filters.Chat(OTP_GROUP_ID) & ~filters.COMMAND, handle_otp_group_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text))

    # ── Real-time group member change (leave/join) ──
    from telegram.ext import ChatMemberHandler
    app.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    async def post_init(application):
        global _tg_app
        _tg_app = application
        asyncio.create_task(scheduled_membership_check(application))
        asyncio.create_task(green_api_monitor(application))
        await start_http_server()
        start_all_panels(application)  # ── OTP Panels শুরু করো ──

    app.post_init = post_init

    logger.info("="*50)
    logger.info("🚀 Starting NEXION Bot (Python)...")
    logger.info(f"📢 Main Channel: {MAIN_CHANNEL_ID}")
    logger.info(f"💬 Chat Group: {CHAT_GROUP_ID}")
    logger.info(f"📨 OTP Group: {OTP_GROUP_ID}")
    logger.info("="*50)

    app.run_polling(allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])

if __name__ == "__main__":
    main()
