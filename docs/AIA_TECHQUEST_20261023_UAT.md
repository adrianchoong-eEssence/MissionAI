# AIA TechQuest disposable UAT

This branch is based on certified Core P0 commit `56419bc48c74ce76aa4a996723ceec1b36720b66`. The prepared disposable event is `AIA-TECH-20261023-UAT` / `AIAUAT`; it contains no production roster or final AIA grouping decision.

The UAT uses Personal Key / PREASSIGNED identity, canonical attendance, one-Captain activation gating, the Theme Park Race OPEN_MISSION_BOARD, private evidence, participation-prorated scoring, facilitator rubric review, canonical P0-C adjustments, Mission Control, and a five-second public projector. Its 25 Quest teams × 10 certification participants are synthetically marked in Mission Control. Mission content is configurable UAT content only; ride names are limited to previously verified library references.

Run the generated UAT SQL only in an owner-selected non-production Core v2 environment. Before live setup: replace the synthetic roster, set the final team configuration, site-reconnoitre and approve every ride mapping, set the return deadline in canonical EventState, and obtain owner approval to install `supabase/045_aia_tech_public_projector_projection.sql`. Run `python scripts/aia_250_certification.py --execute` only in an authorised staging environment; plan mode lists the exact credentials/runtime requirements.
