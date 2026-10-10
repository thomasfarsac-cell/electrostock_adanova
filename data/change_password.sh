#!/bin/bash

FILE="auth_password.hash"

if [ ! -f "$FILE" ]; then
    echo "Fichier $FILE introuvable"
    exit 1
fi

# Demande du mot de passe (caché)
read -s -p "Nouveau mot de passe: " PASSWORD
echo
read -s -p "Confirmer: " CONFIRM
echo

if [ "$PASSWORD" != "$CONFIRM" ]; then
    echo "Les mots de passe ne correspondent pas"
    exit 1
fi

# Génération du hash via Python
HASH=$(python3 - <<EOF
import hashlib, base64, os

password = """$PASSWORD"""
iterations = 260000

salt = base64.b64encode(os.urandom(16)).decode()

dk = hashlib.pbkdf2_hmac(
    'sha256',
    password.encode(),
    base64.b64decode(salt),
    iterations
)

hash_ = base64.urlsafe_b64encode(dk).decode()

print(f"pbkdf2_sha256\${iterations}\${salt}\${hash_}")
EOF
)

# Écriture dans le fichier
echo "$HASH" > "$FILE"

echo "Mot de passe mis à jour dans $FILE"
