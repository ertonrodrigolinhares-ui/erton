# Testes que saíram junto (tests/test_core_resilience.py, classe CoreResilienceTests)

Precisam de `from memory import answer_cache` no começo do arquivo.

```python
    def test_answer_cache_ignores_commands_and_time_sensitive_questions(self):
        self.assertFalse(answer_cache.is_cacheable_question("Open Safari"))
        self.assertFalse(answer_cache.is_cacheable_question("What is the weather today?"))
        self.assertTrue(answer_cache.is_cacheable_question("What is polymorphism?"))

    def test_answer_cache_round_trip_uses_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            answer_cache, "CACHE_PATH", Path(directory) / "answers.json"
        ):
            answer_cache.save_cached_answer("What is polymorphism?", "One interface, multiple implementations.")
            self.assertIn("multiple implementations", answer_cache.get_cached_answer("What is polymorphism?"))
```
