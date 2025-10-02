// static/admin/map_picker.js
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const box = document.getElementById('adminMapPicker');
        if (!box) return;
        const xInput = document.getElementById('id_map_x_pct');
        const yInput = document.getElementById('id_map_y_pct');

        const pin = document.createElement('div');
        Object.assign(pin.style, {
            position: 'absolute', width: '16px', height: '16px', borderRadius: '999px',
            background: '#ff4d4f', border: '2px solid #fff', transform: 'translate(-50%,-100%)',
            pointerEvents: 'none', boxShadow: '0 4px 10px rgba(0,0,0,.25)'
        });
        box.appendChild(pin);

        function placeFromInputs() {
            if (!xInput.value || !yInput.value) return;
            pin.style.left = xInput.value + '%';
            pin.style.top = yInput.value + '%';
        }

        placeFromInputs();

        box.addEventListener('click', (e) => {
            const rect = box.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width) * 100;
            const y = ((e.clientY - rect.top) / rect.height) * 100;
            xInput.value = x.toFixed(2);
            yInput.value = y.toFixed(2);
            placeFromInputs();
        });
    });
})();
