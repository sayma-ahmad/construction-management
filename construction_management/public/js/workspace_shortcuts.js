// Copyright (c) 2026, TechnoTribes and contributors
// For license information, please see license.txt

(function () {
	function init_shortcut_icon_support() {
		// Layer 1: Decorate ShortcutWidget prototype if available
		if (frappe.widget?.widget_factory?.shortcut) {
			const proto = frappe.widget.widget_factory.shortcut.prototype;
			if (!proto._cm_icon_patched) {
				proto._cm_icon_patched = true;
				const original_set_title = proto.set_title;
				proto.set_title = function (max_chars) {
					original_set_title.call(this, max_chars);
					if (this.icon && this.title_field && !this.title_field.find(".cm-shortcut-icon").length) {
						const $icon = $(frappe.utils.icon(this.icon, "sm", "", "", "mr-2 cm-shortcut-icon"));
						$icon.css({
							"vertical-align": "middle",
							"margin-right": "8px",
							"display": "inline-flex",
						});
						this.title_field.prepend($icon);
					}
				};

				const original_set_actions = proto.set_actions;
				proto.set_actions = function () {
					original_set_actions.call(this);
					if (this.icon && this.title_field && !this.title_field.find(".cm-shortcut-icon").length) {
						const $icon = $(frappe.utils.icon(this.icon, "sm", "", "", "mr-2 cm-shortcut-icon"));
						$icon.css({
							"vertical-align": "middle",
							"margin-right": "8px",
							"display": "inline-flex",
						});
						this.title_field.prepend($icon);
					}
				};
			}
		}
	}

	function render_missing_workspace_icons() {
		const route = frappe.get_route ? frappe.get_route() : [];
		if (!route || !route.length) return;

		// Check if we are on a workspace page (e.g. /app/construction-management)
		const workspace = frappe.workspace;
		const shortcuts = workspace?.page_data?.shortcuts?.items || [];
		if (!shortcuts.length) return;

		$(".shortcut-widget-box").each(function () {
			const $box = $(this);
			const $title = $box.find(".widget-title");
			if (!$title.length || $title.find(".cm-shortcut-icon").length) return;

			const label = $title.text().trim();
			const match = shortcuts.find(
				(s) => (s.label || "").trim() === label || __(s.label || "").trim() === label
			);
			if (match && match.icon) {
				const $icon = $(frappe.utils.icon(match.icon, "sm", "", "", "mr-2 cm-shortcut-icon"));
				$icon.css({
					"vertical-align": "middle",
					"margin-right": "8px",
					"display": "inline-flex",
				});
				$title.prepend($icon);
			}
		});
	}

	// Initialize immediately if frappe is ready
	init_shortcut_icon_support();

	// Initialize on standard Frappe lifecycle hooks
	$(document).ready(() => {
		init_shortcut_icon_support();
		render_missing_workspace_icons();
	});

	$(document).on("app_ready", () => {
		init_shortcut_icon_support();
		render_missing_workspace_icons();
	});

	$(document).on("page-change", () => {
		init_shortcut_icon_support();
		setTimeout(render_missing_workspace_icons, 100);
		setTimeout(render_missing_workspace_icons, 500);
	});

	if (window.frappe?.router?.on) {
		frappe.router.on("change", () => {
			setTimeout(render_missing_workspace_icons, 100);
			setTimeout(render_missing_workspace_icons, 500);
		});
	}
})();
