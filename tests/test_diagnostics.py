import unittest
from datetime import datetime, timezone

from app.diagnostics import build_roaming_diagnostics, rf_execution_state

NOW = datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)

class RoamingDiagnosticsTests(unittest.TestCase):
    def test_live_rssi_and_return_to_previous_ap(self):
        states=[{"clientId":"c1","name":"Doorbell","macAddress":"00:11","roamCount24h":9,
                 "currentApName":"Garage","status":"FREQUENT_ROAMING"}]
        clients=[{"id":"c1","macAddress":"00:11","channel":11,"signalDbm":-81,"ssid":"Example"}]
        events=[
            {"ts":"2026-10-08T15:00:00+00:00","client_id":"c1","from_ap_id":"A","to_ap_id":"B"},
            {"ts":"2026-10-08T15:10:00+00:00","client_id":"c1","from_ap_id":"B","to_ap_id":"A"},
        ]
        row=build_roaming_diagnostics(states,clients,events,NOW)[0]
        self.assertTrue(row["connectedNow"])
        self.assertEqual(row["signalDbm"],-81)
        self.assertEqual(row["recentBounceCount"],1)
        self.assertIn("weak",row["diagnostic"])
        self.assertIn("back-and-forth",row["diagnostic"])

    def test_unvalidated_positive_signal_never_becomes_dbm(self):
        states=[{"clientId":"c","name":"Phone","macAddress":"aa:bb","roamCount24h":4,"status":"ACTIVE_ROAMING"}]
        client=[{"id":"other","macAddress":"AA:BB","signalDbm":73}]
        row=build_roaming_diagnostics(states,client,[],NOW)[0]
        self.assertTrue(row["connectedNow"])
        self.assertIsNone(row["signalDbm"])
        self.assertIn("RSSI unavailable",row["diagnostic"])

    def test_offline_client_not_misrepresented_as_connected(self):
        row=build_roaming_diagnostics(
            [{"clientId":"missing","name":"Historical","roamCount24h":0,"status":"STABLE"}],
            [],[],NOW
        )[0]
        self.assertFalse(row["connectedNow"])
        self.assertIn("stale",row["diagnostic"])

    def test_only_recent_complete_event_pairs_make_bounce(self):
        states=[{"clientId":"1","name":"Device","roamCount24h":2,"status":"ROAMED"}]
        events=[
            {"ts":"2026-10-01T00:00:00+00:00","client_id":"1","from_ap_id":"B","to_ap_id":"A"},
            {"ts":"2026-10-08T15:00:00+00:00","client_id":"1","from_ap_id":"A","to_ap_id":"B"},
        ]
        row=build_roaming_diagnostics(states,[],events,NOW)[0]
        self.assertEqual(row["recentBounceCount"],0)

class RFDecisionTests(unittest.TestCase):
    def test_enabled_without_candidates_is_monitoring_not_applied(self):
        result=rf_execution_state(True,True,True,{"items":[{"status":"KEEP"}]},[])
        self.assertEqual(result["phase"],"MONITORING")
        self.assertEqual(result["candidateCount"],0)
        self.assertFalse(result["automaticScanEnabled"])

    def test_rollback_warning_overrides_disabled_state(self):
        result=rf_execution_state(False,True,True,{},[
            {"id":4,"ap_name":"Garage","status":"ROLLBACK_REQUIRED","phase":"AWAITING_ROLLBACK"}])
        self.assertEqual(result["phase"],"ROLLBACK_REQUIRED")
        self.assertEqual(result["activeTestCount"],1)

    def test_candidate_without_scan_backing_is_not_proven(self):
        result=rf_execution_state(True,True,True,{"items":[
            {"status":"CONSIDER_CHANGE","testableChange":True,"scanBackedRecommendation":False}]},[])
        self.assertEqual(result["phase"],"CANDIDATES")
        self.assertEqual(result["scanBackedCandidateCount"],0)
        self.assertIn("None scan-backed",result["detail"])

    def test_unverified_write_blocks_auto(self):
        result=rf_execution_state(True,True,False,{},[])
        self.assertEqual(result["phase"],"BLOCKED")

if __name__ == "__main__":
    unittest.main()
