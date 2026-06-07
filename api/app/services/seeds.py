"""Demo seed — spec section 7. Idempotent via full reset in admin router."""
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import (
    Person, Wallet, WalletMember, Envelope, EnvelopeCategory,
    WalletBlock, Merchant, MccCategoryMap,
)
from app.core.security import hash_pin
from datetime import date

MCC_SEED = {
    "5411": "food", "5422": "food", "5499": "food",
    "5942": "study", "5943": "study", "8299": "study",
    "7230": "grooming", "7298": "grooming",
    "5812": "entertainment", "5813": "entertainment", "7832": "entertainment", "7994": "entertainment",
    "4111": "transport", "4121": "transport", "5541": "transport",
    "5912": "health", "8011": "health",
    "4814": "airtime_data",
    "5921": "alcohol", "7995": "gambling",
}

def seed(db: Session) -> dict:
    for mcc, cat in MCC_SEED.items():
        db.add(MccCategoryMap(mcc=mcc, category=cat))

    mma  = Person(phone_e164="+26771000001", full_name="Mma Boitumelo",
                  date_of_birth=date(1978, 3, 14), pin_hash=hash_pin("9999"))
    neo  = Person(phone_e164="+26771000002", full_name="Neo Boitumelo",
                  date_of_birth=date(2007, 1, 20), pin_hash=hash_pin("1234"))
    kabelo = Person(phone_e164="+26771000003", full_name="Kabelo M")
    kea  = Person(phone_e164="+26771000004", full_name="Kea (Cape Town)")
    db.add_all([mma, neo, kabelo, kea]); db.flush()

    w = Wallet(owner_id=neo.id, tap_limit_bwp=Decimal("200"), cum_tap_limit_bwp=Decimal("500"))
    db.add(w); db.flush()
    db.add(WalletMember(wallet_id=w.id, person_id=mma.id, role="guardian"))
    db.add(WalletMember(wallet_id=w.id, person_id=kabelo.id, role="contributor"))
    db.add(WalletMember(wallet_id=w.id, person_id=kea.id, role="contributor"))

    def env(name, bal, cats, open_contrib=False):
        e = Envelope(wallet_id=w.id, name=name, balance_bwp=Decimal(bal),
                     open_to_contributions=open_contrib, rule_set_by=mma.id)
        db.add(e); db.flush()
        for c in cats:
            db.add(EnvelopeCategory(envelope_id=e.id, category=c))
        return e

    env("Food", "350", ["food"])
    env("Study", "100", ["study"])
    env("Entertainment", "50", ["entertainment"])
    env("Grooming", "0", ["grooming"], open_contrib=True)

    db.add(WalletBlock(wallet_id=w.id, category="alcohol", set_by=mma.id))
    db.add(WalletBlock(wallet_id=w.id, category="gambling", set_by=mma.id))

    merchants = [
        Merchant(display_name="Choppies Gaborone West", raw_descriptor="CHOPPIES GW 0042",
                 category="food", mcc="5411", rail="sticker", payout_method="eft",
                 payout_ref="FNB-000111", settlement_policy="weekly", commission_bps=250),
        Merchant(display_name="Campus Bookshop", category="study", mcc="5942",
                 rail="sticker", payout_method="orange_money", payout_ref="71000010"),
        Merchant(display_name="Liquorama Gabs", category="alcohol", mcc="5921",
                 rail="card", payout_method="eft", payout_ref="ABSA-000222"),
        Merchant(display_name="Kgale Salon", category="grooming", mcc="7230",
                 rail="sticker", payout_method="orange_money", payout_ref="71000011"),
        Merchant(display_name="Mma Dineo's Tuck Shop", category="food",
                 rail="sticker", payout_method="orange_money", payout_ref="71000012"),
    ]
    db.add_all(merchants)
    db.commit()
    return {"wallet_id": str(w.id), "owner": neo.full_name,
            "merchants": {m.display_name: str(m.id) for m in merchants}}