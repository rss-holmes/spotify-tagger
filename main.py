from typing import Any, Dict, TypedDict
import eyed3
from pathlib import Path
import os
import traceback
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from mutagen.id3 import ID3NoHeaderError, ID3, TIT2, TALB, TPE1, TPE2, COMM, TCOM, TCON, TDRC, TRCK
from mutagen import File
from mutagen.flac import FLAC
from mutagen.easyid3 import EasyID3

import logging
logging.basicConfig(filename='runtime.log', level=logging.INFO, filemode='w', format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')

class ID3_data(TypedDict):
    title: str
    artist: str
    album: str
    track_number: str

class SpotifyDataExtractor(object):

    def __init__(self):

        self.client_id = '503b4341f09e4daeaa91a795be8d8216'
        self.client_secret = '7a8326c98b364a27a3fd5e0632816806'
        client_credentials = SpotifyClientCredentials(client_id = self.client_id, client_secret = self.client_secret)
        self.spotify = spotipy.Spotify(client_credentials_manager = client_credentials)
        self.input_folder_path = ''
        self.extension_list = ['.mp3', '.flac']
        self.track_id_dict = {}
        self.non_processed_list = []

    def get_audio_features(self, track_id):

        return self.spotify.audio_features([track_id])

    def get_artists(self, artist_id):

        return self.spotify.artists([artist_id])

    def key_calculation(self, track_data):

        mode_0 = {
        '0' : '5A',
        '1' : '12A',
        '2' : '7A',
        '3' : '2A',
        '4' : '9A',
        '5' : '4A',
        '6' : '11A',
        '7' : '6A',
        '8' : '1A',
        '9' : '8A',
        '10' : '3A',
        '11' : '10A', }

        mode_1 = {
        '0' : '8B',
        '1' : '3B',
        '2' : '10B',
        '3' : '5B',
        '4' : '12B',
        '5' : '7B',
        '6' : '2B',
        '7' : '9B',
        '8' : '4B',
        '9' : '11B',
        '10' : '6B',
        '11' : '1B', }

        if track_data['mode'] == 0:
            track_data['key'] = mode_0[str(track_data['key'])]

        elif track_data['mode'] == 1:
            track_data['key'] = mode_1[str(track_data['key'])]

        return track_data

    def check_title_with_spotify_track_id(self, query):
        
        try:
            results = self.spotify.track(track_id=query['title'])

        except Exception as e:
            logging.info("This track couldnt fetch any data from spotify using the track id. \n")
            results = None

        return results

    def spotify_search(self, query):

        parsed_query = f"{query['title']} {query['artist']}"
        results = self.spotify.search(q = parsed_query, type = 'track')
        results = results['tracks']['items']

        if len(results) == 0:
            logging.info("This track couldnt fetch any data from spotify using title and artist.\n Trying with track_id in title. \n")
            track_data = self.check_title_with_spotify_track_id(query)
            if track_data:
                selection = track_data
            else:
                logging.info("This track couldnt get any match from spotify using both methods. \n")
                logging.info("Adding this track to the Non Processed files list.")
                return None, ''
        
        else:

            logging.info('\nSearch results from spotify :')
            for index, item in enumerate(results, 1):
                logging.info(f"{index}.\n\t"
                    f"Track: {item['name']}\n\t"
                    f"Artist: {item['artists'][0]['name']}\n\t"
                    f"Album: {item['album']['name']}\n\t"
                    f"Track number: {item['track_number']}")
            
            logging.info("Choosing most relevant entry. ")

            selection = results[0]
        
        track_id = selection['id']
        track_name = selection['name']
        popularity = selection['popularity']
        artist_id = selection['artists'][0]['id']
        artist_genres = self.get_artists(artist_id)['artists'][0]['genres']

        track_data = {'track_id': track_id, 'popularity': popularity, 'genres': artist_genres, 'track_name': track_name}

        audio_features = dict(self.get_audio_features(selection['id'])[0])
        track_data.update(audio_features)

        track_data = self.key_calculation(track_data)
        track_data_as_string = self.convert_dict_to_string(track_data)

        return track_data, track_data_as_string

    def convert_dict_to_string(self, track_data):

        comment_string = ''
        for key, value in track_data.items():
            comment_string += f'\n {key}{value}'

        return comment_string


    def set_tags(self, track_data: Dict[str, Any], track_data_as_a_string: str, file_path, file_extension):

        if file_extension == '.mp3':

            # Read ID3 tag or create it if not present
            try: 
                audiofile = ID3(file_path)
            except ID3NoHeaderError:
                logging.info("Adding ID3 header")
                audiofile = ID3()

            audio_file_eyed3 = eyed3.load(file_path)

            comment_string = ''

            for comment in audio_file_eyed3.tag.comments:
                comment_string += str(comment.text)
            
            audiofile.delall("COMM")
            audiofile["COMM"] = COMM(encoding=3, text=comment_string + track_data_as_a_string)
            # audiofile.add(COMM(encoding=3, text=track_data_as_a_string))
            audiofile["TCON"] = TCON(encoding=3, text="; ".join(track_data['genres']))
            audiofile["TIT2"] = TIT2(encoding=3, text=track_data['track_name'])
            # audiofile.update_to_v23()
            # audiofile.save(file_path, v1=0,v2_version=3)
            audiofile.save()
        
        elif file_extension == '.flac':
            audiofile = FLAC(file_path)
            audiofile['title'] = track_data['track_name']
            audiofile['genre'] = "; ".join(track_data['genres'])
            a = list(audiofile.get('comment', ['']))
            a[0] += track_data_as_a_string
            audiofile['comment'] = [*a]
            audiofile.save()

        else : 
            logging.info("File format not recognized while processing")

    def process_track(self, file_path, file_extension):

        logging.info("Processing file :: " + str(file_path))

        audiofile = File(file_path, easy=True)

        if audiofile is not None and audiofile.get("title", None) and audiofile.get("artist", None):

            logging.info("Artist :: " + str(audiofile["artist"][0]))
            logging.info("Title :: " + str(audiofile["title"][0]))

            spotify_query_data_for_track = {'artist': str(audiofile["artist"][0]) , 'title': str(audiofile["title"][0])}
            spotify_data_for_track, spotify_data_for_track_as_a_string = self.spotify_search(spotify_query_data_for_track)

            if spotify_data_for_track is None:
                self.non_processed_list.append(file_path)
            else:
                self.set_tags(spotify_data_for_track, spotify_data_for_track_as_a_string, file_path, file_extension)
            
        else :
            logging.info("The file has no id3 metadata or title or artist name")
            self.non_processed_list.append(file_path)


    def main(self):
        input_folder_path = str(input('Enter the folder path containing the tracks: '))

        try:

            with os.scandir(input_folder_path) as entries:
                for entry in entries:
                    logging.info("-"*100)
                    logging.info("entry name : " + entry.name)
                    if entry.is_file():
                        filename, file_extension = os.path.splitext(entry.path)
                        logging.info("File Extension : " + file_extension)

                        if file_extension in self.extension_list:
                            self.process_track(entry.path, file_extension)
                        else:
                            logging.info("This file does not match the permitted list of extensions.")
                    else :
                        logging.info("This entry is not a file.")

            logging.info("The script has successfully completed processing all files in this folder !!!")

            if len(self.non_processed_list) > 0:
                error_string = ''
                for index, filepath in enumerate(self.non_processed_list, 1):
                    error_string += str(index) + ') ' + str(filepath) + '\n'
                file = open("error.txt", "w") 
                file.write(error_string) 
                file.close() 
                logging.info("The files whose matches could not be found have been written to the errors.txt file. ")
            else:
                logging.info("There were no files which got 0 matches on spotify.")
        
        except Exception as e:
            logging.info("Error in processing. Stacktrace ::: \n" + str(traceback.format_exc()))


if __name__ == '__main__':

    sde = SpotifyDataExtractor()
    sde.main()
    
