# Domainumzug: alte Kartenadresse auf karte.jfr-service.de

**Stand:** 14.11.2026
**Status:** `302`-Weiterleitung aktiv. Umstellung auf `308` und Abschalten der
alten Instanz stehen noch aus.

## Ziel

Alte Lesezeichen und Links auf

```text
https://christoph-moder.de/vmforum-karte/...
```

sollen nicht brechen und auf

```text
https://karte.jfr-service.de/...
```

weitergeleitet werden. Die alte Instanz bleibt zunächst erreichbar, liefert
aber für den Kartenpfad nur noch Redirects aus.

Es handelt sich ausdrücklich um einen HTTP-Redirect, nicht um einen Reverse
Proxy. Die Karte läuft ausschließlich auf der neuen Domain.

## Verhalten

| Alter Pfad | Neuer Pfad |
|---|---|
| `/vmforum-karte` | `https://karte.jfr-service.de/` |
| `/vmforum-karte/` | `https://karte.jfr-service.de/` |
| `/vmforum-karte/karte.html` | `https://karte.jfr-service.de/karte.html` |
| `/vmforum-karte/leaflet/...` | `https://karte.jfr-service.de/leaflet/...` |
| `/vmforum-karte/shared/...` | `https://karte.jfr-service.de/shared/...` |
| `/vmforum-karte/geo-handler.php?l=...` | `https://karte.jfr-service.de/geo-handler?l=...` |

GET-Query-Parameter bleiben erhalten, insbesondere die Filterparameter
`name`, `vm`, `lr`, `tr`, `other` und `tag`.

## Serverkonfiguration

Die alte Instanz läuft auf Apache 2.4. Die VHosts für `christoph-moder.de`
(Port 80 und Port 443) liegen in `/etc/apache2/apache2.conf`. In beiden VHosts
stehen die beiden folgenden Regeln vor den übrigen `RedirectMatch`-Regeln:

```apache
RedirectMatch 302 ^/vmforum-karte/geo-handler\.php$ https://karte.jfr-service.de/geo-handler
RedirectMatch 302 ^/vmforum-karte(?:/(.*))?$        https://karte.jfr-service.de/$1
```

Die erste Regel biegt den alten `geo:`-Handler auf den neuen, öffentlichen
Handler um. Die zweite Regel übernimmt den kompletten restlichen Pfad über
`$1`. Bei `/vmforum-karte` und `/vmforum-karte/` ist `$1` leer; das Ziel endet
dann auf `/`.

`RedirectMatch` stammt aus `mod_alias`. Das Modul ist bereits aktiv, weil die
alte Konfiguration `RedirectMatch` für andere Pfade verwendet.

## Basic Auth

Der alte Kartenpfad ist weiterhin über einen `<Directory>`-Block geschützt.
Die VHost-Redirects werden vor der Authentifizierung verarbeitet, daher darf
auf der Weiterleitungsroute kein `WWW-Authenticate` erscheinen.

Falls nach einem Reload doch `401` kommt, ist der Fallback `mod_rewrite` im
VHost. `RewriteRule` läuft ebenfalls vor der Authentifizierung:

```apache
RewriteEngine On
RewriteRule ^/vmforum-karte/karte\.html$      https://karte.jfr-service.de/karte.html [R=302,L,QSA]
RewriteRule ^/vmforum-karte/geo-handler\.php$ https://karte.jfr-service.de/geo-handler [R=302,L,QSA]
RewriteRule ^/vmforum-karte/(.*)$             https://karte.jfr-service.de/$1 [R=302,L,QSA]
RewriteRule ^/vmforum-karte$                  https://karte.jfr-service.de/ [R=302,L,QSA]
```

`QSA` erhält die Query-Parameter.

## Deployment

```bash
sudo cp -a /etc/apache2/apache2.conf /etc/apache2/apache2.conf.bak-phase10
sudoedit /etc/apache2/apache2.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

`configtest` muss `Syntax OK` liefern. Ein `reload` genügt; ein `restart` ist
nicht nötig.

## Verifikation

```bash
for u in \
  'https://christoph-moder.de/vmforum-karte' \
  'https://christoph-moder.de/vmforum-karte/' \
  'https://christoph-moder.de/vmforum-karte/karte.html' \
  'https://christoph-moder.de/vmforum-karte/karte.html?other=%23tag' \
  'https://christoph-moder.de/vmforum-karte/leaflet/leaflet.js' \
  'https://christoph-moder.de/vmforum-karte/shared/vmforum_members.json' \
  'https://christoph-moder.de/vmforum-karte/geo-handler.php?l=geo:50,11' \
  'https://www.christoph-moder.de/vmforum-karte/karte.html' \
  'http://christoph-moder.de/vmforum-karte/karte.html'; do
  echo "===== $u"
  curl -sSI "$u" | sed -n '1p;/^[Ll]ocation:/p;/^[Ww][Ww][Ww]-[Aa]uthenticate:/p'
done
```

Erwartet wird überall `302` mit passendem `Location` und ohne
`WWW-Authenticate`. Bei `?other=%23tag` muss die Query im `Location` stehen.
`geo-handler.php?l=geo:50,11` muss auf
`https://karte.jfr-service.de/geo-handler?l=geo:50,11` zeigen.

## Rollback

```bash
sudo cp -a /etc/apache2/apache2.conf.bak-phase10 /etc/apache2/apache2.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Es werden keine Daten oder alten Dateien gelöscht. Der Rollback ist rein
konfigurationsseitig.

## Später: 308 und Abschalten der alten Instanz

Nach einer Beobachtungsphase:

1. `302` auf `308` umstellen.
2. Den alten Datengrabber auf dem Server stoppen (Cron oder systemd-Timer),
   damit keine alten Daten mehr geschrieben werden.
3. Den alten Docroot `/var/www/christoph/vmforum-karte` archivieren oder
   entfernen. Die Redirect-Regeln bleiben bestehen.
4. Den Basic-Auth-Block für den alten Kartenpfad entfernen, wenn er nicht mehr
   benötigt wird.
5. Die Dokumentation auf den zentralen Docker-Betrieb unter
   `https://karte.jfr-service.de` umstellen.

## Bekannte Einschränkung

Beim ersten Aufruf eines alten Filter-Lesezeichens geht die Query durch die
Login-Weiterleitung der neuen Instanz verloren. nginx leitet ohne gültige
Sitzung auf `/login?next=/karte.html` um; die Filterparameter werden dabei
nicht in `next` übernommen. Nach der Anmeldung funktioniert das Lesezeichen
erneut, weil dann eine Sitzung auf der neuen Domain existiert.

Eine saubere Korrektur wäre ein separater Schritt im neuen nginx- und
Auth-Service und ist nicht Teil des Apache-Redirects.
