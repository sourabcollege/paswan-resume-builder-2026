from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user, logout_user
from app.profile import bp
from app.extensions import db
import re


@bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    if request.method == 'POST':
        data = request.get_json() or request.form.to_dict()

        current_user.first_name = data.get('first_name', current_user.first_name)
        current_user.last_name = data.get('last_name', current_user.last_name)
        current_user.phone = data.get('phone', current_user.phone)
        current_user.location = data.get('location', current_user.location)
        current_user.headline = data.get('headline', current_user.headline)
        current_user.bio = data.get('bio', current_user.bio)
        current_user.profile_visibility = data.get('profile_visibility', current_user.profile_visibility)

        profile_data = current_user.profile_data or {}
        profile_data['linkedin_url'] = data.get('linkedin_url', profile_data.get('linkedin_url', ''))
        profile_data['github_url'] = data.get('github_url', profile_data.get('github_url', ''))
        profile_data['skills'] = data.get('skills', profile_data.get('skills', []))
        current_user.profile_data = profile_data

        db.session.commit()

        if request.is_json:
            return jsonify({"success": True, "message": "Profile updated!"})
        flash("Profile updated successfully!", "success")
        return redirect(url_for('profile.edit'))

    profile_data = current_user.profile_data or {}
    skills = profile_data.get('skills', [])

    completion = 0
    fields = [
        current_user.first_name,
        current_user.last_name,
        current_user.phone,
        current_user.location,
        current_user.headline,
        current_user.bio,
        profile_data.get('linkedin_url'),
        profile_data.get('github_url'),
        skills,
    ]
    for f in fields:
        if f:
            completion += 11
    completion = min(100, completion + 10)

    return render_template(
        'profile/edit.html',
        user=current_user,
        profile_data=profile_data,
        skills=skills,
        completion=completion,
    )


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        data = request.get_json() or request.form.to_dict()
        action = data.get('action', 'update_settings')

        if action == 'change_password':
            return _handle_change_password(data)
        elif action == 'update_settings':
            return _handle_update_settings(data)

    return render_template('profile/settings.html', user=current_user)


def _handle_change_password(data):
    current_pwd = data.get('current_password', '')
    new_pwd = data.get('new_password', '')

    if not current_user.check_password(current_pwd):
        return jsonify({"success": False, "message": "Current password is incorrect"}), 400

    if len(new_pwd) < 12:
        return jsonify({"success": False, "message": "Password must be at least 12 characters"}), 400

    if not any(c.islower() for c in new_pwd):
        return jsonify({"success": False, "message": "Password must include a lowercase letter"}), 400
    if not any(c.isupper() for c in new_pwd):
        return jsonify({"success": False, "message": "Password must include an uppercase letter"}), 400
    if not any(c.isdigit() for c in new_pwd):
        return jsonify({"success": False, "message": "Password must include a number"}), 400
    if not re.search(r'[^A-Za-z0-9]', new_pwd):
        return jsonify({"success": False, "message": "Password must include a symbol"}), 400

    current_user.set_password(new_pwd)
    db.session.commit()
    return jsonify({"success": True, "message": "Password updated successfully!"})


def _handle_update_settings(data):
    current_user.timezone = data.get('timezone', current_user.timezone)
    current_user.locale = data.get('locale', current_user.locale)
    current_user.profile_visibility = data.get('profile_visibility', current_user.profile_visibility)

    weekly = data.get('weekly_summary_enabled')
    if weekly is not None:
        if isinstance(weekly, str):
            current_user.weekly_summary_enabled = weekly.lower() in ('true', '1', 'on', 'yes')
        else:
            current_user.weekly_summary_enabled = bool(weekly)

    db.session.commit()
    return jsonify({"success": True, "message": "Settings saved successfully!"})


@bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    data = request.get_json() or request.form.to_dict()
    password = data.get('password', '')

    if not current_user.check_password(password):
        return jsonify({"success": False, "message": "Incorrect password"}), 400

    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    return jsonify({"success": True, "message": "Account deleted", "redirect": url_for('main.index')})