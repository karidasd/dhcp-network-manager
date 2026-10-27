# 🌐 DHCP Server & Network IP Manager (Python)

Ένα πλήρες, σύγχρονο σύστημα αυτόματης απόδοσης και διαχείρισης διευθύνσεων IP (**DHCP Server**) για υπολογιστές και συσκευές τοπικού δικτύου (LAN), γραμμένο σε **Python** με διαδραστικό **Web Dashboard (GUI)**.

---

## 🚀 Πώς να το ξεκινήσετε (Quick Start)

### Τρόπος 1: Με διπλό κλικ (Windows)
Κάντε διπλό κλικ στο αρχείο **`start.bat`** μέσα στον φάκελο `DHCP_Server`.
Αυτό θα ξεκινήσει αυτόματα τον server και θα ανοίξει το Web Dashboard στον browser σας στη διεύθυνση:
👉 **`http://localhost:8080`**

### Τρόπος 2: Μέσω τερματικού / PowerShell
```bash
cd c:\Users\karid\Documents\PROGRAMS_ANTIGRAVITY\DHCP_Server
py server.py
```

> **Σημείωση:** Δεν χρειάζεται εγκατάσταση καμίας εξωτερικής βιβλιοθήκης (`pip`)! Χρησιμοποιεί αποκλειστικά τη στάνταρ βιβλιοθήκη της Python (Python Standard Library).

---

## 🎯 Δυνατότητες & Χαρακτηριστικά

1. **Αυτόματη Απόδοση IP (Dynamic Host Configuration Protocol)**:
   - Πλήρης υλοποίηση του κύκλου **DORA** (**D**iscover ➔ **O**ffer ➔ **R**equest ➔ **A**cknowledge).
   - Αυτόματος έλεγχος διαθεσιμότητας και αποφυγή διπλότυπων IPs (IP conflict prevention).
   - Παρακολούθηση διάρκειας μίσθωσης (Lease Duration) και αυτόματη λήξη/ανανέωση.

2. **Web Dashboard (Σύγχρονο Γραφικό Περιβάλλον)**:
   - **Επισκόπηση Στατιστικών**: Συνολικό Pool IPs, Ενεργές Μισθώσεις, Ελεύθερες IPs, Στατικές Δεσμεύσεις.
   - **Μπάρα Χρήσης Pool (Utilization Bar)**: Ποσοστό κατανάλωσης διευθύνσεων σε πραγματικό χρόνο.
   - **Πίνακας Ενεργών Leases**: Όνομα υπολογιστή, IP, MAC address, χρόνος λήξης, και κουμπί άμεσης ανάκλησης/αποδέσμευσης (Revoke).

3. **Προσομοιωτής Πελάτη (Client Simulator)**:
   - Δοκιμάστε ζωντανά την είσοδο νέων υπολογιστών με ένα κλικ («Αίτηση IP»).
   - Οπτική απεικόνιση των βημάτων DORA με κινούμενα badges.
   - Αυτόματη παραγωγή τυχαίων MAC addresses και ονομάτων υπολογιστών.

4. **Στατικές Δεσμεύσεις (Static IP Reservations / IP Binding)**:
   - Δέσμευση συγκεκριμένης IP για συγκεκριμένη MAC διεύθυνση (π.χ. για εκτυπωτές, NAS, Servers).

5. **Ρυθμίσεις Δικτύου σε Πραγματικό Χρόνο**:
   - Παραμετροποίηση εύρους (Start IP - End IP).
   - Subnet Mask, Gateway, DNS Servers, Lease Time, Domain Name.

6. **Ζωντανό Αρχείο Καταγραφής (Live Event Log Feed)**:
   - Χρωματικά κωδικοποιημένα logs για κάθε μήνυμα (DISCOVER, OFFER, REQUEST, ACK, RELEASE, WARNING).

7. **Υποστήριξη Πραγματικού Δικτύου (Real Socket UDP Port 67)**:
   - Περιλαμβάνει UDP socket listener για πραγματικά broadcast πακέτα DHCP (RFC 2131) όταν εκτελείται με δικαιώματα διαχειριστή (Run as Administrator) σε απομονωμένο εργαστηριακό δίκτυο.

---

## 🧠 Πώς λειτουργεί το Πρωτόκολλο DHCP (DORA);

Όταν ένας υπολογιστής συνδέεται σε ένα τοπικό δίκτυο (Ethernet ή Wi-Fi), δεν γνωρίζει ποια IP μπορεί να χρησιμοποιήσει:

```mermaid
sequenceDiagram
    autonumber
    actor PC as Υπολογιστής (Client)
    participant DHCP as DHCP Server

    PC->>DHCP: 1. DHCPDISCOVER (Broadcast UDP 68 -> 67)<br/>"Υπάρχει κάποιος DHCP Server; Χρειάζομαι IP!"
    DHCP->>PC: 2. DHCPOFFER (UDP 67 -> 68)<br/>"Σου προτείνω την IP 192.168.1.100, Gateway 192.168.1.1"
    PC->>DHCP: 3. DHCPREQUEST (Broadcast)<br/>"Αποδέχομαι την IP 192.168.1.100!"
    DHCP->>PC: 4. DHCPACK (Acknowledge)<br/>"Κατοχυρώθηκε! Μπορείς να τη χρησιμοποιήσεις."
```

---

## 📁 Δομή Αρχείων Φακέλου

```
c:\Users\karid\Documents\PROGRAMS_ANTIGRAVITY\DHCP_Server\
│
├── start.bat            <- Εκκινητής Windows (Double-click για άνοιγμα)
├── server.py            <- HTTP API Server & Web Controller
├── dhcp_engine.py       <- Κύριος πυρήνας λογικής DHCP & DORA state machine
├── test_dhcp.py         <- Αυτοματοποιημένα τεστ επαλήθευσης
├── README.md            <- Αναλυτικός οδηγός χρήσης
│
└── web/
    └── index.html       <- Responsive Dashboard γραφικού περιβάλλοντος
```
