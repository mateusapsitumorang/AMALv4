import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

class PasswordValidator:
    def validate(self, password, user=None):
        # 1. Minimal 8 karakter dan maksimal 16 karakter
        if not (8 <= len(password) <= 16):
            raise ValidationError(
                _("Passwords must be between 8 and 16 characters long."),
                code='password_length',
            )

        # 2. Tidak boleh ada huruf/angka/simbol yang sama berurutan 3 kali (misal 'aaa' atau '111')
        if re.search(r'(.)\1{2,}', password):
            raise ValidationError(
                _("Passwords must not contain three consecutive identical characters."),
                code='password_consecutive',
            )

        # 3. Harus ada minimal 1 huruf besar, 1 huruf kecil, 1 angka, dan 1 simbol
        if not re.search(r'[A-Z]', password):
            raise ValidationError(_("Passwords must contain at least one uppercase letter."), code='password_no_upper')
        
        if not re.search(r'[a-z]', password):
            raise ValidationError(_("Passwords must contain at least one lowercase letter."), code='password_no_lower')
        
        if not re.search(r'\d', password):
            raise ValidationError(_("Passwords must contain at least one number."), code='password_no_number')
        
        # Simbol diartikan sebagai karakter selain huruf dan angka
        if not re.search(r'[^A-Za-z0-9]', password):
            raise ValidationError(_("Passwords must contain at least one symbol."), code='password_no_symbol')

        # 4. Tidak boleh mengandung nama yang ada di username
        if user and user.username:
            if user.username.lower() in password.lower():
                raise ValidationError(
                    _("Passwords must not contain your username."),
                    code='password_contains_username',
                )

    def get_help_text(self):
        return