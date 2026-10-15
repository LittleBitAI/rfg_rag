---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline: Adopting RRSI adoption lower bound and held-out for self-improvement"
pr: 41
merged: 2026-10-15
branch: "feature/golden-adoption-floor"
---

# golden_pipeline: Adopting RRSI adoption lower bound and held-out for self-improvement

What. Divide the bundle of plans into `bundle_id` hashes: train 60 · validation 20 · held-out 20 (`golden_pipeline/adoption.py`). - round(`r{n}`) calls only the train bundle. Release candidates and failure logs come only from train. - New prevention rules are compared against the current policy in the validation bundle (`v{n}`) by pairing bundles, and the bootstrap (1000 times, one-sided 95%) lower bound is …

Why. golden_pipeline follows google-research/rrsi. Until now, prevention rules were unconditionally attached whenever a failure code was generated. Because RRSI's adoption lower bound (adopting only improvements excluding noise) and held-out (not used for selection) were missing, it was impossible to know even if ineffective rules were accumulating.

Source. PR #41 · `feature/golden-adoption-floor`
