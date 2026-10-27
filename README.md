# 🌐 DHCP Server & Network IP Manager

[![Tests](https://github.com/karidasd/dhcp-network-manager/actions/workflows/test.yml/badge.svg)](https://github.com/karidasd/dhcp-network-manager/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-SQLite%203-003B57.svg)](https://www.sqlite.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#)

Ένα πλήρες, σύγχρονο σύστημα αυτόματης απόδοσης και διαχείρισης διευθύνσεων IP (**DHCP Server**) για υπολογιστές και συσκευές τοπικού δικτύου (LAN), γραμμένο σε **Python** με **SQLite Persistence**, **Ping Online Monitoring**, **Rogue Device Security Detection** και **Διαδραστικό Οπτικό Χάρτη Τοπολογίας (Topology Map)**.

---

## 🚀 Πώς να το ξεκινήσετε (Quick Start)

### Τρόπος 1: Με διπλό κλικ (Windows)
Κάντε διπλό κλικ στο αρχείο **`start.bat`**.
Αυτό θα ξεκινήσει αυτόματα τον server και θα ανοίξει το Web Dashboard στον browser σας στη διεύθυνση:
👉 **`http://localhost:8080`**

### Τρόπος 2: Μέσω τερματικού / PowerShell
```bash
cd DHCP_Server
py server.py
# Ή σε Linux/macOS: python3 server.py
```

> **Zero Dependencies:** Δεν χρειάζεται καμία εγκατάσταση με `pip`! Χρησιμοποιεί αποκλειστικά τη στάνταρ βιβλιοθήκη της Python (`http.server`, `socket`, `sqlite3`, `threading`).

---

## 🎯 Δυνατότητες & Χαρακτηριστικά

### 1. ⚡ Αυτόματη Απόδοση IP (DHCP Protocol)
- Πλήρης υλοποίηση του κύκλου **DORA** (**D**iscover ➔ **O**ffer ➔ **R**equest ➔ **A**cknowledge).
- Αυτόματος έλεγχος διαθεσιμότητας και αποφυγή διπλότυπων IP διευθύνσεων.
- Παρακολούθηση διάρκειας μίσθωσης (Lease Duration) και αυτόματη λήξη/ανανέωση.

### 2. 💾 Μόνιμη Αποθήκευση Δεδομένων (SQLite Persistence)
- Όλες οι ενεργές μισθώσεις, οι στατικές κρατήσεις και οι ρυθμίσεις δικτύου αποθηκεύονται αυτόματα στην τοπική βάση **`dhcp_leases.db`**.
- Ακόμα και αν κλείσει ο server, τα δεδομένα παραμένουν ασφαλή και ανακτώνται κατά την επανεκκίνηση.

### 3. 🗺️ Διαδραστικός Οπτικός Χάρτης Δικτύου (Live Topology Map)
- Dynamic HTML5 Canvas rendering της τοπολογίας του τοπικού δικτύου.
- Κεντρικός κόμβος (DHCP Gateway) συνδεδεμένος με όλες τις ενεργές συσκευές σε πραγματικό χρόνο.
- Οπτική ένδειξη κατάστασης σύνδεσης και IP.

### 4. 🟢 Ζωντανός Έλεγχος Συσκευών (Ping / Online Health Probe)
- Αυτόματο background scanning μέσω ICMP Ping.
- Ένδειξη **Online (πράσινο)** / **Offline (γκρι)** για κάθε συνδεδεμένη συσκευή.

### 5. 🛡️ Ασφάλεια & Ειδοποιήσεις (Rogue Device & Threshold Alerts)
- **Rogue Device Detection:** Εντοπίζει και ειδοποιεί άμεσα στο UI όταν μια άγνωστη MAC address εμφανιστεί στο δίκτυο.
- **Pool Exhaustion Warning:** Προειδοποίηση όταν η χρήση του εύρους IP ξεπεράσει το 85%.

### 6. 📊 Εξαγωγή Αναφορών (Export CSV & JSON)
- Άμεση εξαγωγή όλων των leases και των συσκευών σε αρχείο Excel/CSV (`/api/export/csv`).
- Πλήρες JSON backup API (`/api/export/json`).

### 7. 🔒 Στατικές Δεσμεύσεις (Static Reservations / IP Binding)
- Δέσμευση συγκεκριμένης IP για συγκεκριμένη MAC διεύθυνση (π.χ. Server, NAS, Εκτυπωτής).

### 8. 📡 Πραγματικό Δίκτυο (UDP Port 67)
- Περιλαμβάνει UDP socket listener για πραγματικά broadcast πακέτα DHCP (RFC 2131) όταν εκτελείται με δικαιώματα διαχειριστή.

---

## 🧠 Πώς λειτουργεί το Πρωτόκολλο DHCP (DORA);

```mermaid
sequenceDiagram
    autonumber
    actor PC as Υπολογιστής (Client)
    participant DHCP as DHCP Server (Python)

    PC->>DHCP: 1. DHCPDISCOVER (Broadcast UDP 68 -> 67)<br/>"Υπάρχει κάποιος DHCP Server; Χρειάζομαι IP!"
    DHCP->>PC: 2. DHCPOFFER (UDP 67 -> 68)<br/>"Σου προτείνω την IP 192.168.1.100, Gateway 192.168.1.1"
    PC->>DHCP: 3. DHCPREQUEST (Broadcast)<br/>"Αποδέχομαι την IP 192.168.1.100!"
    DHCP->>PC: 4. DHCPACK (Acknowledge)<br/>"Κατοχυρώθηκε στη βάση SQLite! Μπορείς να τη χρησιμοποιήσεις."
```

---

## 📁 Δομή Αρχείων

```
DHCP_Server/
│
├── .github/
│   └── workflows/
│       └── test.yml         <- GitHub Actions CI Pipeline
│
├── start.bat                <- Εκκινητής Windows (Double-click)
├── server.py                <- HTTP API Server & Web Controller
├── dhcp_engine.py           <- Κύριος πυρήνας διανομής IP & DORA engine
├── db_manager.py            <- Διαχειριστής βάσης δεδομένων SQLite 3
├── test_dhcp.py             <- Αυτοματοποιημένα τεστ επαλήθευσης
├── README.md                <- Τεκμηρίωση & οδηγός χρήσης
├── .gitignore               <- Εξαιρέσεις Git (db, pycache κ.α.)
│
└── web/
    └── index.html           <- Responsive Web Dashboard & Topology Map
```
