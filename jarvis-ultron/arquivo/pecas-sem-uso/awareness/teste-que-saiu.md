# Teste que saiu junto (tests/test_core_resilience.py, classe CoreResilienceTests)

Precisa de `from awareness.engine import AwarenessEngine` no começo do arquivo.

```python
    def test_awareness_state_is_copied_and_bounded(self):
        engine = AwarenessEngine(lambda *_: None)
        engine.set_goal("Audit JARVIS")
        for index in range(25):
            engine.record_event(f"event-{index}")
        state = engine.get_state()
        self.assertEqual(state.current_goal, "Audit JARVIS")
        self.assertEqual(len(state.recent_events), 20)
```
