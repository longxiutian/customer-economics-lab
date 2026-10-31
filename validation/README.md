# Validation for release 1.7.0

These receipts describe the current dataset, report and companion. Historical receipts remain in their prior Git tags.

- [Release scope](release.json): versions, artifact hashes and checks.
- [Data migration](data-migration.json): retained operational rows are byte-identical and in their original order.
- [Fresh model runs](refit-v1.7.0.json): two independent processes; 20 fitted/model-challenge files agree exactly on the same host.
- [Report reproduction](reproducibility-v1.7.0.json): two fresh reporting processes; all 122 canonical files agree. This replay preserves the newly fitted models.
- [Test evidence](pytest.txt): 187 unique tests have passing results across a full run and a final 17-test follow-up; the initial failures and transient reference-setup errors are stated.
- [Visual review](visual-qa.json): all 50 report pages and 13 native PowerPoint slides, with numerical chart/table matching recorded separately.
- [Public-boundary audit](private-boundary.json): current public files and embedded artifacts; no private future labels published.

Both skills pass their schema validator. Companion provenance is stored in [teaching](../teaching/companion-provenance.json). The actual public ZIP download receipt is attached after publication to the v1.7.0 GitHub release.

The optional forecasting challenge requires an instructor answer file reconciled to dataset 5.0 before future scoring. No private outcomes were read, regenerated or used to choose models in this revision; see the [challenge contract](../docs/model-challenge.md).
