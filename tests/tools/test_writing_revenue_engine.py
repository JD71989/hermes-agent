import json,os,sys,unittest,importlib.util
P=r"C:\Users\jamie\AppData\Local\hermes\automation\news_media\writing_revenue_engine.py"
spec=importlib.util.spec_from_file_location("wre",P); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class T(unittest.TestCase):
 def test_score(self): self.assertGreater(m.score("best business software guide"),5)
 def test_gate(self):
  x=m.score("how to choose a tool"); self.assertGreaterEqual(x,6)
if __name__=="__main__": unittest.main()
