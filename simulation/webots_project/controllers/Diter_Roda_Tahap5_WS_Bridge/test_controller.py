#!/usr/bin/env python3
"""
SIMPLE TEST CONTROLLER - Debug version
"""
print("=== LOADING TEST CONTROLLER ===")

try:
    from controller import Robot
    print("[OK] Robot imported")
    
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    print(f"[OK] Path: {os.path.dirname(__file__)}")
    
    from Diter_Roda_Tahap5_controller import BroneDiterFusion
    print("[OK] BroneDiterFusion imported")
    
    print("\n=== STARTING CONTROLLER ===")
    bot = BroneDiterFusion()
    print("[OK] Controller initialized")
    
    bot.run()
    
except Exception as e:
    print(f"\n!!! ERROR: {e}")
    import traceback
    traceback.print_exc()
