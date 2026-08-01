.PHONY: test check audit

test:
	zsh tests/test_tab_shader.zsh
	python3 -m unittest discover -s tests -v

audit:
	python3 scripts/audit_public_tree.py

check: test audit
	zsh -n iterm-tab-shader.zsh
	sh -n scripts/claude-statusline.sh
	python3 -m compileall -q scripts tests
