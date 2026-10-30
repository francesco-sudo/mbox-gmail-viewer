# MBOX Gmail-like Viewer

Web viewer in sola lettura per archivi email in formato `.mbox`, con interfaccia ispirata a Gmail.

## Caratteristiche

- Lettura di uno o più file MBOX da una cartella locale.
- Elenco messaggi con mittente, destinatario, oggetto, anteprima, data e allegati.
- Visualizzazione HTML sicura tramite sanitizzazione e iframe con `sandbox`.
- Visualizzazione alternativa in testo semplice.
- Download e anteprima di allegati comuni: immagini e PDF.
- Ricerca avanzata in stile Gmail:
  - `from:utente@example.com`
  - `to:destinatario@example.com`
  - `subject:fattura`
  - `after:2024-01-01`
  - `before:2024-12-31`
  - `has:attachment`
  - combinazione di più filtri.
- Paginazione lato server.
- Indice SQLite locale ricostruibile.
- Docker e Docker Compose.
- Nessuna autenticazione: usare solo su rete locale fidata.

## Requisiti

- Ubuntu Server 22.04 LTS o 24.04 LTS.
- Docker.
- Docker Compose.
- Browser moderno.
- Porta host predefinita: `8081`.

## Installazione Docker su Ubuntu Server

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
