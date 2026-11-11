
(() => {
    const menuButton = document.querySelector('.menu-toggle');
    const navigation = document.querySelector('#main-nav');

    if (menuButton && navigation) {
        const setMenuOpen = (open) => {
            menuButton.setAttribute('aria-expanded', String(open));
            menuButton.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
            navigation.classList.toggle('is-open', open);
        };

        menuButton.addEventListener('click', () => {
            setMenuOpen(menuButton.getAttribute('aria-expanded') !== 'true');
        });

        navigation.addEventListener('click', (event) => {
            if (event.target.closest('a')) {
                setMenuOpen(false);
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
                setMenuOpen(false);
                menuButton.focus();
            }
        });

        document.addEventListener('click', (event) => {
            if (!navigation.contains(event.target) && !menuButton.contains(event.target)) {
                setMenuOpen(false);
            }
        });
    }

    const staffMenuButton = document.querySelector('.staff-menu-toggle');
    const staffSidebar = document.querySelector('#staff-sidebar');
    const staffSidebarBackdrop = document.querySelector('.staff-sidebar-backdrop');

    if (staffMenuButton && staffSidebar && staffSidebarBackdrop) {
        const setStaffMenuOpen = (open) => {
            staffMenuButton.setAttribute('aria-expanded', String(open));
            staffMenuButton.setAttribute('aria-label', open ? 'Close administration menu' : 'Open administration menu');
            staffSidebar.setAttribute('aria-hidden', String(!open));
            staffSidebar.classList.toggle('is-open', open);
            staffSidebarBackdrop.classList.toggle('is-open', open);
            document.body.classList.toggle('staff-menu-open', open);
        };

        staffMenuButton.addEventListener('click', () => {
            setStaffMenuOpen(staffMenuButton.getAttribute('aria-expanded') !== 'true');
        });

        staffSidebarBackdrop.addEventListener('click', () => setStaffMenuOpen(false));
        staffSidebar.addEventListener('click', (event) => {
            if (event.target.closest('a')) {
                setStaffMenuOpen(false);
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && staffMenuButton.getAttribute('aria-expanded') === 'true') {
                setStaffMenuOpen(false);
                staffMenuButton.focus();
            }
        });
    }

    document.querySelectorAll('.staff-password-toggle').forEach((toggle) => {
        const password = document.getElementById(toggle.getAttribute('aria-controls'));
        if (!password) {
            return;
        }

        toggle.addEventListener('click', () => {
            const reveal = password.type === 'password';
            password.type = reveal ? 'text' : 'password';
            toggle.textContent = reveal ? 'Hide' : 'Show';
            toggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
            toggle.setAttribute('aria-pressed', String(reveal));
        });
    });

    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });
})();
