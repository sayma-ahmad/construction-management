// Copyright (c) 2026, TechnoTribes and contributors
// For license information, please see license.txt

// Make the Construction Dashboard the desk home page for users who can open it.
(function () {
	const DASHBOARD_ROLES = ["System Manager", "Projects Manager", "Projects User"];

	function is_home_route(route) {
		if (!route) return false;
		// v15 opens the "Home" workspace; v16 opens the apps grid at the desk root.
		return (
			!route.length ||
			(route.length === 1 && !route[0]) ||
			(route[0] === "Workspaces" && (route[1] || "").toLowerCase() === "home")
		);
	}

	function redirect_home_to_dashboard() {
		if (!window.frappe?.get_route || !frappe.user?.has_role) return;
		if (!frappe.user.has_role(DASHBOARD_ROLES)) return;
		if (!is_home_route(frappe.get_route())) return;

		window.history.replaceState(null, "", frappe.router.make_url(["construction-dashboard"]));
		frappe.router.route();
	}

	// Wait until the desk has rendered the current route before switching to the dashboard.
	$(document).on("page-change", () => setTimeout(redirect_home_to_dashboard, 0));
})();
