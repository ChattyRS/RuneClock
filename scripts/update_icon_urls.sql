-- The icon_url for items appears to contain a number that may be updated with game revisions.
-- It appears that old icons may be deleted after some time.
-- Hence this may need to be updated with some frequency for the items icons to be able to load.
-- See example below to update the number in all icon urls to '1782809081938'. Just replace with the desired number.

-- Preview changes
SELECT icon_url AS before, regexp_replace(icon_url, '\d+(_obj_big)', '1782809081938\1') AS after
FROM osrs_items
WHERE icon_url ~ '\d+_obj_big';

-- Execute the change
UPDATE osrs_items
SET icon_url = regexp_replace(icon_url, '\d+(_obj_big)', '1782809081938\1')
WHERE icon_url ~ '\d+_obj_big';