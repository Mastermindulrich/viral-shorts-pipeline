"""Plain-English recovery instructions. Never executes commands or exposes raw errors."""
import shlex
import pipeline as p


def explain(error, action=''):
    text=str(error).lower()
    command='cd '+shlex.quote(str(p.ROOT))+' && .venv/bin/python '
    auth=command+'pipeline.py auth'
    def answer(title, steps, command_text=None):
        return dict(title=title,steps=steps,command=command_text)
    if any(x in text for x in ('invalid_grant','expired or revoked','authorization expired','run auth','read-only permission')):
        return answer('Your YouTube sign-in needs to be renewed. Your clips are still saved.',[
            'Open Terminal on your Mac. Paste the command below and press Enter.',
            'In the browser, sign in with the Google account that owns Viral Moment Clips. Choose that channel if asked, then allow access.',
            'Refresh this dashboard. Click Verify YouTube connection in the sidebar.',
            'Open Review & publish and publish your existing clips again. You do not need to make them again.'],auth)
    if any(x in text for x in ('upload already attempted','uncertain upload','duplicate upload','already published from this moment')):
        return answer('Publishing is paused to avoid posting the same clip twice.',[
            'Open YouTube Studio → Content and check whether this clip is already there.',
            'If it is there, keep that upload and choose a different moment.',
            'If it is missing or you are unsure, expand Activity and diagnostics below and share the diagnostics for help. Do not delete upload records or repeatedly press Publish.'])
    if 'connected to' in text or 'expected_channel' in text:
        return answer('The connected YouTube channel does not match your publishing channel.',[
            'Run the command below in Terminal.',
            'Choose the Google account and channel for Viral Moment Clips and allow access.',
            'Refresh the page, click Verify YouTube connection, then publish the saved clips.'],auth)
    if 'daily upload cap' in text:
        return answer('You have reached the app’s daily publishing limit.',[
            'Wait until the next UTC day, then publish the existing clips.',
            'Or open Settings → Daily upload attempt limit, increase it, and click Save settings. This does not change YouTube’s own limits.'])
    if any(x in text for x in ('quota','ratelimit','rate limit','429','uploadlimitexceeded')):
        return answer('YouTube is temporarily limiting requests or uploads.',[
            'Wait before trying again; repeatedly clicking will not reset the limit.',
            'For publishing, first check YouTube Studio → Content for the clip before retrying.',
            'If it still fails the next day, expand Activity and diagnostics and share the report.'])
    if 'ollama' in text or 'local ai editor' in text:
        return answer('The local AI editor could not finish or is not ready.',[
            'Open the Ollama app on your Mac and keep your Mac awake.',
            'Open Settings → Re-run setup check. Follow any missing-model instructions shown there.',
            'If the model is missing, run the command below in Terminal.',
            'Retry Make clips → Already imported video to reuse your downloaded source.'], 'ollama pull qwen2.5:7b')
    if any(x in text for x in ('final context review','complete scenes','transcript is empty','continuous speech')):
        return answer('The editor could not confirm a complete, understandable spoken scene.',[
            'Any automatic context-review recovery runs before this message appears.',
            'For dance, sports action or silent footage: open Make clips from a link → Already imported video, select the source, and expand Choose a visual moment manually.',
            'Preview the source, enter a start, end and English title, then create the visual preview.',
            'For spoken content, try a clearer interview or another short English source. If many sources fail, share Activity and diagnostics.'])
    if 'english dialogue' in text or 'music' in text or 'eligible' in text:
        return answer('This source does not meet your saved content rules.',[
            'Choose an English-speaking source. Standalone official music releases are excluded.',
            'For allowed visual dance or action content, import a suitable source and choose a visual moment manually.'])
    if '20 minutes' in text or 'finished video' in text:
        return answer('This source is too long or is still live.',[
            'Choose a finished YouTube video no longer than 20 minutes.',
            'Paste its individual video link into Make clips from a link and click Make clips.'])
    if any(x in text for x in ('https youtube','https youtube','youtube video link','one video link')):
        return answer('The app needs a link to one YouTube video.',[
            'Open the video on YouTube, click Share, then Copy link.',
            'Paste it into Video link. Do not use a channel or playlist link.'])
    if any(x in text for x in ('ffmpeg','ffprobe','merged video','libass','subtitles filter')):
        return answer('The video-processing tools could not finish this job.',[
            'Open Terminal and run the command below.',
            'Close and reopen the dashboard, then run Settings → Re-run setup check.',
            'Retry the imported source. If it fails again, share Activity and diagnostics.'],'brew install ffmpeg-full')
    if any(x in text for x in ('no space','disk full','cannot allocate memory','out of memory')):
        return answer('Your Mac ran out of storage or working memory.',[
            'Close other large apps and check free storage in System Settings → General → Storage.',
            'Free space using files you no longer need. Keep this app’s upload records and credentials.',
            'Retry with a shorter source and Editing options → Fastest · base.'])
    if any(x in text for x in ('missing local input','file is missing','no such file','filenotfound')):
        return answer('A video or required file is missing.',[
            'For a missing preview, delete that unpublished draft in Review & publish and generate it again from the source link.',
            'If a setup file is missing, open Settings → Re-run setup check and follow its instructions.',
            'If that does not fix it, share Activity and diagnostics.'])
    if 'changed' in text and any(x in text for x in ('approval','render','metadata')):
        return answer('The preview or its details changed after it was prepared.',[
            'Review the current title and audience, then click Publish now again to approve the current version.',
            'If it still fails, regenerate that unpublished draft and review its new preview.'])
    if any(x in text for x in ('another task','already running','task stopped','interrupted')):
        return answer('Another job is running, or the previous worker stopped.',[
            'Check the progress banner. If work is running, wait for it to finish.',
            'Keep your Mac awake. If the job stopped, refresh and retry clip making from Already imported video.',
            'For a stopped upload, check YouTube Studio before retrying.'])
    if any(x in text for x in ('update validation','local code changes','install the mac launcher')):
        return answer('The app update could not be completed.',[
            'Do not reset or delete your project files.',
            'Expand Activity and diagnostics below, download the report, and share it for help.',
            'For validation failures, also share data/logs/update-checks.log from your project folder.'])
    if any(x in text for x in ('timed out','timeout','connection','network','503','502','ssl','unreachable','download','private video','unavailable','sign in to confirm')):
        return answer('The app could not reach a service or access the source video.',[
            'Check your internet connection and open the original video on YouTube to confirm it is available.',
            'Temporary download and search failures are retried automatically before the task stops.',
            'Try another publicly accessible source if this one is private, restricted or removed.',
            'For a failed upload, check YouTube Studio before retrying. If this continues, share Activity and diagnostics.'])
    return answer('The app could not finish this action. The exact cause needs checking.',[
        'Keep your existing clips; you do not need to start the project again.',
        'Expand Activity and diagnostics at the bottom of the page and click Download diagnostics to share.',
        'Share that report and say which button you clicked. For publishing, check YouTube Studio before retrying to avoid a duplicate.'])
