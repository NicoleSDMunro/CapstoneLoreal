import unittest
import numpy as np
import pandas as pd

from smartlaunch_core import (
    month, parse_matrix, Matrices, forward_cover, simulate_inventory,
    metrics, critical_window, deadline, actionable_lots, compare_alternative,
    analog_forecast, monte_carlo, benchmark_log_errors,
)

def p(value):
    return pd.Period(value,freq="M")

class TestSmartLaunch(unittest.TestCase):
    def test_months(self):
        self.assertEqual(month("jun/26"),p("2026-06"))
        self.assertEqual(month("2026-10"),p("2026-10"))
        self.assertEqual(month(pd.Timestamp("2026-09-15")),p("2026-09"))

    def test_pv_parser(self):
        raw=pd.DataFrame([
          ["Fechamento","nov/25","dez/25","jan/26"],
          ["nov/25",30,40,50],
          ["dez/25",32,42,52],
        ])
        matrix=parse_matrix(raw)
        self.assertEqual(matrix.loc[p("2025-11"),p("2025-12")],40)
        self.assertEqual(len(matrix.index),2)

    def test_forward_cover_example_from_methodology(self):
        stock=np.array([[190.,0.,0.,0.]])
        demand=np.array([[10.,80.,55.,90.]])
        coverage=forward_cover(stock,demand,0)
        expected=60+30*55/90
        self.assertAlmostEqual(float(coverage[0]),expected,places=4)

    def test_lost_sales_no_negative_inventory(self):
        stock,lost,coverage=simulate_inventory(
            10,np.array([5,0],dtype=float),
            np.array([[20,2]],dtype=float))
        self.assertTrue((stock>=0).all())
        self.assertAlmostEqual(lost[0,0],5)
        self.assertAlmostEqual(lost[0,1],2)

    def test_inventory_probabilities(self):
        demand=np.tile(np.array([[20.,30.,10.,10.,10.,10.]]),(1000,1))
        result=metrics(400,np.zeros(6),demand,limit=180,window=4)
        self.assertAlmostEqual(result["fill_rate"],1)
        self.assertEqual(len(result["excess_risk"]),4)
        self.assertTrue(np.all((result["excess_risk"]>=0)&(result["excess_risk"]<=1)))

    def test_lead_time_filters_lots(self):
        closure=p("2026-06")
        months=[p("2026-07"),p("2026-11")]
        eligible=actionable_lots(closure,months,np.array([100.,100.]),16)
        self.assertEqual([x[1] for x in eligible],[p("2026-11")])

    def test_reused_scenarios(self):
        d=np.tile(np.array([[8.,8.,8.,8.]]),(1000,1))
        receipts=np.array([15.,30.,30.,30.])
        base=metrics(50,receipts,d,limit=180,window=4)
        altered=compare_alternative(base,50,receipts,d,2,-50,180,4)
        self.assertGreaterEqual(altered["lost_extra"],0)
        self.assertEqual(altered["change"],-50)

    def test_simulation_reproducible(self):
        a=monte_carlo(np.array([10.,11.]),np.array([-2.,3.,1.]))
        b=monte_carlo(np.array([10.,11.]),np.array([-2.,3.,1.]))
        np.testing.assert_array_equal(a,b)

    def test_analog_no_future_sales(self):
        dates=pd.period_range("2025-01",periods=12,freq="M")
        mat=pd.DataFrame(index=dates,columns=dates,dtype=float)
        for index in dates:
            for target in dates:
                if target<=index:mat.loc[index,target]=30.
        # Realized sales from version t+1's value at t
        groups={"A_1":Matrices(mat),
                "P1":Matrices(pd.DataFrame([[np.nan]*12],index=[p("2025-11")],columns=dates))}
        answer=analog_forecast(groups,"P1",["A_1"],p("2025-11"),p("2025-12"),3)
        self.assertIsNotNone(answer)
        self.assertTrue(np.all(np.isfinite(answer)))

if __name__=="__main__":
    unittest.main()
