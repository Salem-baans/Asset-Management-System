#!/usr/bin/env bash

# نستخدم هذا الأمر للتأكد من أن المنطق داخل if __name__ == '__main__': يتم تنفيذه
python -m app

# ثم نشغل الخادم
gunicorn app:app