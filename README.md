# tv-clean-lists

TV lists for the **TV Clean** iPhone app: which preinstalled apps each TV model can safely have
switched off. `lists.json` is rebuilt every day by `.github/workflows/build.yml`, and TV Clean checks
this repo for a newer one when it starts (**TV lists → Check for updates**).

## What's in lists.json

- **Reviewed lists:** the CleanYourTV Android app's own lists
  (https://github.com/udhaykumarbala/cleanyourtv-app), taken from its newest release APK unchanged,
  marked `"reviewed": true`. Their matches and pre-ticked apps were reviewed by that app's maintainers.
- **Community lists:** every other list in the Clean Your TV project
  (https://github.com/Gathin23/cleanyourtv, `examples/<folder>/debloat.txt`), converted by
  `build_lists.py` and marked `"reviewed": false`. Every app on them starts unticked, so nothing is
  switched off unless it is chosen; the TV match comes from the model code and codename in each
  list's description. Lists whose description names neither are left out (`"skipped"`).

TV Clean never switches off the Play Store, system services, the current home screen, the keyboard or
the screensaver, whatever a list says, and saves a restore point on the TV before changing anything.

## Building it yourself

```
git clone --depth 1 https://github.com/Gathin23/cleanyourtv upstream
unzip -p cleanyourtv-X.Y.Z.apk tv/cleanyour/core/spec/profiles.json > reviewed.json
python3 build_lists.py reviewed.json upstream/examples lists.json
```

`build_lists.py` checks its output (format, ids, package names, every list able to match a TV) and
fails rather than write a bad file; TV Clean checks a download again before using it.

## Licence

The lists are the work of the Clean Your TV authors and contributors and the CleanYourTV app
authors, under the MIT licence:

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files, to deal in the Software without restriction, subject to including
the copyright notice and this permission notice in all copies. THE SOFTWARE IS PROVIDED "AS IS",
WITHOUT WARRANTY OF ANY KIND.

`build_lists.py` and the workflow are MIT too.
