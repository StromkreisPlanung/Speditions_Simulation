# -*- coding: utf-8 -*-
"""
Spyder Editor

# Spedition Strommanagement Simulation – Vollständiges Streamlit-Programm

import random
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from fpdf import FPDF
import tempfile
import os
import qrcode

# --------------------------------------------------
# Datenmodell & Simulation
# --------------------------------------------------

def generate_pv_power(hour):
    hour_of_day = hour % 24
    if 6 <= hour_of_day <= 18:
        return max(0, (1 - abs(12 - hour_of_day)/6) * 200)
    else:
        return 0

class Battery:
    def __init__(self, capacity_kwh, charge_rate_kw, discharge_rate_kw):
        self.capacity = capacity_kwh
        self.charge_rate = charge_rate_kw
        self.discharge_rate = discharge_rate_kw
        self.soc = capacity_kwh / 2

    def charge(self, power_kw, duration_h):
        charged = min(power_kw * duration_h, self.capacity - self.soc, self.charge_rate * duration_h)
        self.soc += charged
        return charged

    def discharge(self, power_kw, duration_h):
        discharged = min(power_kw * duration_h, self.soc, self.discharge_rate * duration_h)
        self.soc -= discharged
        return discharged

class Truck:
    def __init__(self, arrival_hour, truck_type):
        self.arrival_hour = arrival_hour
        self.truck_type = truck_type
        if truck_type == "klein":
            self.energy_needed_kwh = random.randint(50, 150)
        elif truck_type == "mittel":
            self.energy_needed_kwh = random.randint(150, 250)
        else:
            self.energy_needed_kwh = random.randint(250, 400)
        self.energy_loaded_kwh = 0

    def load(self, available_energy_kwh):
        load = min(available_energy_kwh, self.energy_needed_kwh - self.energy_loaded_kwh)
        self.energy_loaded_kwh += load
        return load

def run_simulation(sim_days, min_trucks_per_day, max_trucks_per_day, battery_capacity_kwh, charge_rate_kw, discharge_rate_kw, grid_limit_kw):
    HOURS_PER_DAY = 24
    SIMULATION_HOURS = HOURS_PER_DAY * sim_days

    battery = Battery(battery_capacity_kwh, charge_rate_kw, discharge_rate_kw)
    trucks = []

    for day in range(sim_days):
        num_trucks = random.randint(min_trucks_per_day, max_trucks_per_day)
        for _ in range(num_trucks):
            arrival_hour = day * 24 + random.randint(6, 20)
            truck_type = random.choice(["klein", "mittel", "groß"])
            trucks.append(Truck(arrival_hour, truck_type))

    battery_soc = []
    pv_production = []
    truck_energy_loaded = []
    grid_usage = []
    pv_surplus = []
    truck_type_counts = {"klein": [], "mittel": [], "groß": []}

    for hour in range(SIMULATION_HOURS):
        pv_power_kw = generate_pv_power(hour)
        pv_production.append(pv_power_kw)

        trucks_this_hour = [t for t in trucks if t.arrival_hour == hour]
        trucks_this_hour.sort(key=lambda x: {"groß": 0, "mittel": 1, "klein": 2}[x.truck_type])

        available_energy_kwh = pv_power_kw
        surplus_energy = 0
        grid_energy = 0

        types_loaded_this_hour = {"klein": 0, "mittel": 0, "groß": 0}

        for truck in trucks_this_hour:
            if available_energy_kwh > 0:
                loaded = truck.load(available_energy_kwh)
                available_energy_kwh -= loaded
                if loaded > 0:
                    types_loaded_this_hour[truck.truck_type] += 1

        if available_energy_kwh > 0:
            charged = battery.charge(available_energy_kwh, 1)
            available_energy_kwh -= charged

        for truck in trucks_this_hour:
            remaining_need = truck.energy_needed_kwh - truck.energy_loaded_kwh
            if remaining_need > 0:
                discharged = battery.discharge(remaining_need, 1)
                truck.load(discharged)

        for truck in trucks_this_hour:
            remaining_need = truck.energy_needed_kwh - truck.energy_loaded_kwh
            if remaining_need > 0:
                grid_load = min(grid_limit_kw, remaining_need)
                truck.load(grid_load)
                grid_energy += grid_load

        surplus_energy = available_energy_kwh

        battery_soc.append(battery.soc)
        truck_energy_loaded.append(sum(t.energy_loaded_kwh for t in trucks))
        grid_usage.append(grid_energy)
        pv_surplus.append(surplus_energy)

        truck_type_counts["klein"].append(types_loaded_this_hour["klein"])
        truck_type_counts["mittel"].append(types_loaded_this_hour["mittel"])
        truck_type_counts["groß"].append(types_loaded_this_hour["groß"])

    truck_data = {
        'arrival_day': [t.arrival_hour // 24 for t in trucks],
        'energy_needed': [t.energy_needed_kwh for t in trucks],
        'energy_loaded': [t.energy_loaded_kwh for t in trucks]
    }
    df_trucks = pd.DataFrame(truck_data)

    daily_stats = df_trucks.groupby('arrival_day').agg(
        total_trucks=('energy_needed', 'count'),
        avg_load_percentage=('energy_loaded', lambda x: (x.sum() / (x.count() * 200)) * 100)
    ).reset_index()

    days = list(range(sim_days))
    battery_energy_per_day = [battery_soc[(day+1)*24 - 1] for day in days]
    grid_energy_per_day = [sum(grid_usage[day*24:(day+1)*24]) for day in days]
    pv_surplus_per_day = [sum(pv_surplus[day*24:(day+1)*24]) for day in days]

    return daily_stats, battery_energy_per_day, grid_energy_per_day, pv_surplus_per_day, truck_type_counts, trucks, sim_days * 24

# --------------------------------------------------
# Streamlit App UI
# --------------------------------------------------

st.title("Spedition Strommanagement Simulation")

sim_days = st.slider("Anzahl der Tage", 1, 30, 7)
min_trucks = st.slider("Minimale Anzahl LKWs pro Tag", 5, 40, 20)
max_trucks = st.slider("Maximale Anzahl LKWs pro Tag", 20, 100, 50)
battery_capacity = st.slider("Batteriekapazität (kWh)", 100, 1000, 500)
charge_rate = st.slider("Batterie Ladeleistung (kW)", 50, 500, 100)
discharge_rate = st.slider("Batterie Entladeleistung (kW)", 50, 500, 100)
grid_limit = st.slider("Netzlimit (kW)", 50, 300, 100)

if st.button("Simulation starten"):
    daily_stats, battery_energy_per_day, grid_energy_per_day, pv_surplus_per_day, truck_type_counts, trucks, sim_hours = run_simulation(
        sim_days, min_trucks, max_trucks, battery_capacity, charge_rate, discharge_rate, grid_limit
    )

    st.subheader("Ergebnisse")
    st.line_chart(daily_stats.set_index('arrival_day')['total_trucks'])
    st.line_chart(daily_stats.set_index('arrival_day')['avg_load_percentage'])
    st.line_chart(pd.Series(battery_energy_per_day, name="Batterie-SOC Tagesende"))
    st.line_chart(pd.Series(grid_energy_per_day, name="Netzstromverbrauch"))
    st.line_chart(pd.Series(pv_surplus_per_day, name="PV-Überschuss"))

    # LKW-Typen pro Stunde (Stackplot)
    st.subheader("Geladene LKW-Typen pro Stunde")
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.stackplot(range(sim_hours),
                 truck_type_counts["klein"],
                 truck_type_counts["mittel"],
                 truck_type_counts["groß"],
                 labels=["Klein", "Mittel", "Groß"],
                 alpha=0.8)
    ax.legend(loc='upper left')
    ax.set_xlabel("Stunde")
    ax.set_ylabel("Anzahl LKWs")
    ax.set_title("Verteilung der LKW-Typen während der Ladevorgänge")
    ax.grid(True)
    st.pyplot(fig)

    # Tortendiagramme
    st.subheader("Gesamtverteilung der geladenen LKW-Typen")
    total_loaded = {
        "Klein": sum(truck_type_counts["klein"]),
        "Mittel": sum(truck_type_counts["mittel"]),
        "Groß": sum(truck_type_counts["groß"])
    }
    fig2, ax2 = plt.subplots()
    ax2.pie(total_loaded.values(), labels=total_loaded.keys(), autopct='%1.1f%%', startangle=90)
    ax2.axis('equal')
    plt.title("Gesamtanteile geladener LKWs nach Typ")
    st.pyplot(fig2)

    st.subheader("Geladene Energiemenge je LKW-Typ")
    type_energy = {"Klein": 0, "Mittel": 0, "Groß": 0}
    for truck in trucks:
        if truck.truck_type == "klein":
            type_energy["Klein"] += truck.energy_loaded_kwh
        elif truck.truck_type == "mittel":
            type_energy["Mittel"] += truck.energy_loaded_kwh
        elif truck.truck_type == "groß":
            type_energy["Groß"] += truck.energy_loaded_kwh
    fig3, ax3 = plt.subplots()
    ax3.pie(type_energy.values(), labels=type_energy.keys(), autopct='%1.1f%%', startangle=90)
    ax3.axis('equal')
    plt.title("Geladene Energiemenge nach LKW-Typ (kWh)")
    st.pyplot(fig3)

    # PDF-Export mit Logo und QR-Code
    if st.button("PDF-Abschlussbericht erstellen"):
        with tempfile.TemporaryDirectory() as tmpdirname:
            fig2_path = os.path.join(tmpdirname, "lkw_typen_pie.png")
            fig2.savefig(fig2_path)
            fig3_path = os.path.join(tmpdirname, "energie_typen_pie.png")
            fig3.savefig(fig3_path)
            qr_img = qrcode.make("https://www.stromkreis.eu")
            qr_path = os.path.join(tmpdirname, "qr_code.png")
            qr_img.save(qr_path)
            logo_path = "/mnt/data/logo_sk2_cymk_332x167.jpg"

            pdf = FPDF()
            pdf.add_page()
            pdf.image(logo_path, x=60, y=20, w=90)
            pdf.set_font("Arial", 'B', 24)
            pdf.ln(70)
            pdf.cell(0, 10, "Spedition Strommanagement Simulation", ln=True, align='C')
            pdf.ln(20)
            pdf.set_font("Arial", size=16)
            pdf.cell(0, 10, "Projektbericht", ln=True, align='C')
            pdf.cell(0, 10, "Datum: " + pd.Timestamp.now().strftime('%d.%m.%Y'), ln=True, align='C')
            pdf.image(qr_path, x=160, y=250, w=30)
            pdf.set_font("Arial", size=8)
            pdf.set_y(-15)
            pdf.cell(0, 10, "www.stromkreis.eu", ln=True, align='R')

            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "Simulation Report", ln=True, align='C')
            pdf.ln(10)
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, "Gesamtverteilung der geladenen LKWs nach Typ:", ln=True)
            pdf.image(fig2_path, w=170)
            pdf.ln(10)
            pdf.cell(0, 10, "Gesamt geladene Energieverteilung (kWh) je LKW-Typ:", ln=True)
            pdf.image(fig3_path, w=170)
            pdf.ln(10)

            pdf_path = os.path.join(tmpdirname, "abschlussbericht.pdf")
            pdf.output(pdf_path)

            with open(pdf_path, "rb") as f:
                st.download_button("Abschlussbericht herunterladen", data=f, file_name="abschlussbericht.pdf", mime="application/pdf")
 """
