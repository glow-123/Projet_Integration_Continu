-- Schéma de la base. Idempotent (IF NOT EXISTS) : la pipeline l'exécute
-- à chaque lancement pour "mettre en place la base de données".

-- Un fichier CSV traité avec succès = une ligne. Le hash SHA-256 du contenu
-- est UNIQUE : c'est ce qui empêche de traiter deux fois le même fichier.
CREATE TABLE IF NOT EXISTS processed_files (
    id           SERIAL PRIMARY KEY,
    filename     TEXT        NOT NULL,
    file_hash    CHAR(64)    NOT NULL UNIQUE,
    nb_rows      INTEGER     NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Transactions du CSV, avec le flag calculé (montant > 5000)
CREATE TABLE IF NOT EXISTS transactions (
    id                   SERIAL PRIMARY KEY,
    file_id              INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    datetime_transaction TIMESTAMP     NOT NULL,
    iban_origine         VARCHAR(34)   NOT NULL,
    pays_source          CHAR(2)       NOT NULL,
    banque_source        TEXT          NOT NULL,
    iban_destinataire    VARCHAR(34)   NOT NULL,
    pays_destinataire    CHAR(2)       NOT NULL,
    montant              NUMERIC(14,2) NOT NULL CHECK (montant >= 0),
    flag                 BOOLEAN       NOT NULL
);

-- Résultats des traitements, par fichier
CREATE TABLE IF NOT EXISTS total_sent_by_iban (
    file_id INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    iban    VARCHAR(34)   NOT NULL,
    total   NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (file_id, iban)
);

CREATE TABLE IF NOT EXISTS total_sent_by_bank (
    file_id INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    banque  TEXT          NOT NULL,
    total   NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (file_id, banque)
);

CREATE TABLE IF NOT EXISTS total_received_by_iban (
    file_id INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    iban    VARCHAR(34)   NOT NULL,
    total   NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (file_id, iban)
);
