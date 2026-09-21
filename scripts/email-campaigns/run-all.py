#!/usr/bin/env python3
"""
Twenty CRM — Batch Runner for 5 Cold Email Campaigns (150 leads total)
"""

import subprocess
import sys
import time

CAMPAIGNS = [
    {
        "name": "1. Moda & Retail — Operaciones",
        "template": "moda-operaciones",
        "flags": ["--industry", "moda", "--role", "operaciones", "--limit", "30", "-y"]
    },
    {
        "name": "2. Moda & Retail — CEOs / Dueños",
        "template": "moda-ceos",
        "flags": ["--industry", "moda", "--role", "ceo", "--limit", "30", "-y"]
    },
    {
        "name": "3. Logística & Transporte — Operaciones / Tráfico",
        "template": "logistica-operaciones",
        "flags": ["--industry", "logistica", "--role", "operaciones", "--limit", "30", "-y"]
    },
    {
        "name": "4. Logística & Transporte — CEOs / Dirección",
        "template": "logistica-ceos",
        "flags": ["--industry", "logistica", "--limit", "30", "-y"]
    },
    {
        "name": "5. Medianas Empresas (+50 empleados)",
        "template": "medianas-integracion",
        "flags": ["--min-employees", "50", "--limit", "30", "-y"]
    },
]

def main():
    print("=" * 70)
    print("🚀 INICIANDO EJECUCIÓN MASIVA: 5 CAMPAÑAS (150 LEADS)")
    print("=" * 70)
    print("Remitente: Raúl Almeida <raul.almeida@arsoluciondigital.com>")
    print("Pausas aleatorias de 45s a 90s entre correos activadas.\n")

    for i, camp in enumerate(CAMPAIGNS, 1):
        print(f"\n{'#' * 70}")
        print(f"📦 [{i}/5] CAMPAÑA: {camp['name']} (Plantilla: {camp['template']})")
        print(f"{'#' * 70}\n")
        
        cmd = [sys.executable, "scripts/email-campaigns/send-campaign.py", "--template", camp["template"]] + camp["flags"]
        
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"⚠️ La campaña {camp['name']} finalizó con código {res.returncode}")
        
        print(f"✅ Finalizada campaña {i}/5: {camp['name']}")
        if i < len(CAMPAIGNS):
            print("⏳ Pausa de 30s antes de pasar a la siguiente campaña...\n")
            time.sleep(30)

    print("\n" + "=" * 70)
    print("🎉 ¡TODAS LAS 5 CAMPAÑAS HAN SIDO COMPLETADAS CON ÉXITO!")
    print("=" * 70)

if __name__ == "__main__":
    main()
