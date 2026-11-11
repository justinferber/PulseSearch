"""Frozen before loading any owner-side BGE results. Research probes only.
Format: id, query, check_kind, expected value. No model-specific expectations.
"""
CASES=[
 ('x01','How do I join a family physician practice?','top','/nhs-services/gps/how-to-register-with-a-gp-surgery/'),
 ('x02','Where do you apply for a learner motorists licence?','top','/apply-first-provisional-driving-licence'),
 ('x03','How do I join the electoral register?','top','/register-to-vote'),
 ('x04','Rules for checking the local property rates valuation band','top','/council-tax-bands'),
 ('x05','Explain the basics of JS scripting','top','/What_is_JavaScript'),
 ('x06','Tutorial about the HTTP protocol','top','/Web/HTTP'),
 ('x07','Online steps to replace a British passport','top','/renew-adult-passport/renew'),
 ('x08','Where do I arrange an NHS blood sample test?','top','/tests-and-treatments/blood-tests/'),
 ('x09','London Open House 2024 and London Open House 2025','all','/events/london-open-house-2024|/events/london-open-house-2025'),
 ('x10','London 2027 public events excluding Eid','exclude_nonempty','/events/eid'),
 ('x11','London festivals 2026 except St Patrick’s Festival','exclude_nonempty','/events/st-patricks-festival-2026'),
 ('x12','London festivals 2026 excluding London Games Festival','exclude_nonempty','/events/london-games-festival-2026'),
 ('x13','Events listed for London in 2027','year_many','2027'),
 ('x14','Past editions of London Open House','series_many','london open house'),
 ('x15','Diwali on the Square 2038','no_result',''),
 ('x16','Which 2027 Edinburgh concerts were announced?','no_result',''),
 ('x17','London Pride events 2025 but only in Manchester','no_result',''),
 ('x18','Show the weather in Newbury tomorrow','no_result',''),
 ('x19','What time does Eid on the Square 2027 open?','fact_unverified',''),
 ('x20','Are tickets for New Year’s Eve 2026 sold out?','fact_unverified',''),
 ('x21','Which 2027 London festivals are free?','fact_unverified',''),
 ('x22','Does Black on the Square 2027 have wheelchair accessibility?','fact_unverified',''),
 ('x23','What is the cost of a new UK passport now?','fact_unverified',''),
 ('x24','Which London festivals in 2026 were cancelled?','fact_unverified',''),
]
