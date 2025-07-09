#!/usr/bin/env python3
"""Test script to verify WebSocket streaming"""
import time
import sys

print("🚀 Starting WebSocket test...")
time.sleep(1)

for i in range(5):
    print(f"📊 Test message {i+1}/5")
    time.sleep(1)

print("✅ WebSocket test completed!")